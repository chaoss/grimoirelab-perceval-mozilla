# perceval-mozilla [![Build Status](https://travis-ci.org/chaoss/grimoirelab-perceval-mozilla.svg?branch=master)](https://travis-ci.org/chaos/grimoirelab-perceval-mozilla) [![Coverage Status](https://img.shields.io/coveralls/chaoss/grimoirelab-perceval-mozilla.svg)](https://coveralls.io/r/chaoss/grimoirelab-perceval-mozilla?branch=master)

Bundle of Perceval backends for Mozilla ecosystem.

## Backends

The backends currently managed by this package support the next repositories:

* Crates
* Kitsune
* MozillaClub
* ReMo

## Requirements

* Python >= 3.4
* python3-requests >= 2.7
* grimoirelab-toolkit >= 0.1
* perceval >= 0.9.11

## Installation

To install this package you will need to clone the repository first:

```
$ git clone https://github.com/grimoirelab/perceval-mozilla.git
```

In this case, [setuptools](http://setuptools.readthedocs.io/en/latest/) package will be required.
Make sure it is installed before running the next commands:

```
$ pip3 install -r requirements.txt
$ python3 setup.py install
```

## Examples

### Crates

```
$ perceval crates
```

### Kitsune

```
$ perceval kitsune --offset 373990
```

### Mozilla Club Events

```
$ perceval mozillaclub
```

### ReMo
```
$ perceval remo
```

## License

Licensed under GNU General Public License (GPL), version 3 or later.
