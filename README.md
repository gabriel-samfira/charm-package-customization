# charm-package-customization

This charm allows you to customize the installed packaes on a charm. It allows you to specify a PPA and a list of packages that you would like to install. When a PPA is specified, it will be added to the system and the priority of this PPA will be set higher than the default Ubuntu repositories. This allows you to build your own patched versions of packages and install them on your system.

Optionally you can also mark the packages as `hold` so that they are not automatically upgraded by the system.

## Usage

Deploy the charm:

```bash
juju deploy package-customization nova-package-customization
juju config nova-package-customization \
    ppa=ppa:my-ppa/ppa \
    packages="nova-common,nova-compute" \
    hold-packages=true
juju relate nova-package-customization nova-compute
```
