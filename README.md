# perceval-mozilla [![Build Status](https://github.com/chaoss/grimoirelab-perceval-mozilla/workflows/tests/badge.svg)](https://github.com/chaoss/grimoirelab-perceval-mozilla/actions?query=workflow:tests+branch:master+event:push) [![Coverage Status](https://img.shields.io/coveralls/chaoss/grimoirelab-perceval-mozilla.svg)](https://coveralls.io/r/chaoss/grimoirelab-perceval-mozilla?branch=master)[![PyPI version](https://badge.fury.io/py/perceval-mozilla.svg)](https://badge.fury.io/py/perceval-mozilla)

Bundle of Perceval backends for Mozilla ecosystem.

## Backends

The backends currently managed by this package support the next repositories:

* Crates
* Kitsune
* MozillaClub
* ReMo

## Requirements

* Python >= 3.7
* python3-requests >= 2.7
* grimoirelab-toolkit >= 0.2
* perceval >= 0.17.4

## Installation

To install this package you will need to clone the repository first:

```
$ git clone https://github.com/grimoirelab/perceval-mozilla.git
```

Then you can execute the following commands:
```
$ pip3 install -r requirements.txt
$ pip3 install -e .
```

In case you are a developer, you should execute the following commands to install Perceval in your working directory (option `-e`) and the packages of requirements_tests.txt.
```
$ pip3 install -r requirements.txt
$ pip3 install -r requirements_test.txt
$ pip3 install -e .
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
