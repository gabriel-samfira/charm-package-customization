#!/usr/bin/env python3

import logging
import os
import requests
import subprocess
import sortedcontainers

from charms.operator_libs_linux.v0 import apt
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus

logger = logging.getLogger(__name__)


PRIORITY_TEMPLATE = """
Package: *
Pin: release o={release_name}
Pin-Priority: 1001
"""

def install_ppa(ppa):
    subprocess.check_call(["add-apt-repository", "--yes", ppa])


def remove_ppa(ppa):
    subprocess.check_call(["add-apt-repository", "--remove", "--yes", ppa])


def apt_hold(packages):
    if type(packages) is str:
        packages = [packages]
    
    if not packages:
        return
    cmd = ["apt-mark", "hold"]
    cmd.extend(packages)
    subprocess.check_call(cmd)


def apt_unhold(packages):
    if type(packages) is str:
        packages = [packages]
    
    if not packages:
        return
    cmd = ["apt-mark", "unhold"]
    cmd.extend(packages)
    subprocess.check_call(cmd)


def _get_release_name():
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("UBUNTU_CODENAME="):
                return line.split("=")[1].strip()
    raise ValueError("Could not determine release name")


class PackageCustomizationCharm(CharmBase):
    _state = StoredState()
    def __init__(self, *args):
        super().__init__(*args)
        self._state.set_default(
            package_needs_installing=True,
            ppa=None,
            ppa_release_name=None,
            hold_packages=False,
            packages=[])

        self.framework.observe(self.on.config_changed, self.config_changed)

    def _packages(self):
        package_str = self.config.get("packages", "").strip()
        as_list = package_str.split(",")
        ret = sortedcontainers.SortedList()
        for pkg in as_list:
            if pkg.strip() == "":
                continue
            ret.add(pkg)
        return ret

    def _handle_packages(self, force=False):
        hold = self.config.get("hold-packages", False)
        packages = self._packages()
        old_packages = self._state.packages

        if packages != old_packages or force:
            apt_unhold(old_packages)
            if len(packages) > 0:
                apt.add_package(packages, update_cache=True)

        if hold:
            apt_hold(packages)
        else:
            apt_unhold(packages)

        self._state.hold_packages = hold
        self._state.packages = list(packages)
    
    def _ppa_url(self, ppa):
        parts = ppa.split(":", 1)
        if len(parts) == 1:
            raise ValueError("PPA must contain a colon")

        ppa_name = parts[1]
        ppa_parts = ppa_name.split("/", 1)
        if len(ppa_parts) != 2:
            raise ValueError("PPA name must contain a slash")
        return "http://ppa.launchpad.net/{user}/{name}/ubuntu".format(
            user=ppa_parts[0], name=ppa_parts[1])
    
    def _ppa_release_name(self, ppa):
        url = self._ppa_url(ppa)
        release = _get_release_name()
        release_url = "{base_url}/dists/{release_codename}/Release".format(
            base_url=url, release_codename=release)
        response = requests.get(release_url)
        response.raise_for_status()
        for line in response.text.split("\n"):
            if line.startswith("Origin:"):
                return line.split(":", 1)[1].strip()
        raise ValueError("Could not determine release name")

    def _set_ppa_priority(self, ppa_release_name):
        priority = PRIORITY_TEMPLATE.format(release_name=ppa_release_name)
        pref_path = os.path.join("/etc/apt/preferences.d", ppa_release_name)
        with open(pref_path, "w") as f:
            f.write(priority)

    def _unset_ppa_priority(self, ppa_release_name):
        pref_path = os.path.join("/etc/apt/preferences.d", ppa_release_name)
        if os.path.exists(pref_path):
            os.remove(pref_path)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment."""
        logger.info("Beginning config_changed")
        self.unit.status = MaintenanceStatus("Configuring")
        self._handle_ppa_state()
        self._handle_packages(self._state.package_needs_installing)
        self._handle_status_state()
        logger.info("Finished config_changed")

    def _handle_ppa_state(self):
        ppa = self.config.get("ppa", "").strip()
        old_ppa = self._state.ppa
        old_ppa_release_name = self._state.ppa_release_name

        if old_ppa and old_ppa != ppa:
            logger.info("Removing previously installed ppa (%s)", old_ppa)
            remove_ppa(old_ppa)
            self._state.ppa = None
            self._state.package_needs_installing = True
            if old_ppa_release_name:
                self._unset_ppa_priority(old_ppa_release_name)
                self._state.ppa_release_name = None

        if ppa and ppa != old_ppa:
            logger.info("Installing ppa: %s", ppa)
            install_ppa(ppa)
            self._state.ppa = ppa
            ppa_release_name = self._ppa_release_name(ppa)
            self._state.ppa_release_name = ppa_release_name
            self._set_ppa_priority(ppa_release_name)
            self._state.package_needs_installing = True

    def _handle_status_state(self):
        """Parse status output to determine which services are active."""
        hold = self._state.hold_packages
        packages = self._state.packages or []
        message = "Hold: {hold}; Packages: {packages}".format(
            hold=hold, packages=",".join(packages))
        self.unit.status = ActiveStatus(message)


if __name__ == "__main__":
    main(PackageCustomizationCharm)
