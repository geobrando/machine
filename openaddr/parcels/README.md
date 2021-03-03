Parcels
=======

⚠️ This README currently represents an [older, pre-merge state](https://github.com/openaddresses/parcels/tree/pre-move#readme) of Parcels code. ⚠️

### Overview

This script will fetch the latest [state.txt](http://results.openaddresses.io/state.txt) file, and parse as much parcel data as it can.

### Installation

* Tested on Ubuntu 14.04 server. 16GB RAM.

```
# Install pre-requisites and prepare a Python virtual environment.
apt-get install libgdal-dev python3-pip libffi-dev python3-cairo python3-gdal
pip3 install virtualenv
python3 -m virtualenv --system-site-packages ./env && source ./env/bin/activate

# Download all parcel data sources.
git clone https://github.com/openaddresses/openaddresses.git ~/openaddresses

# Install OpenAddresses parcels code.
git clone https://github.com/openaddresses/parcels.git ~/parcels
cd ~/parcels && pip3 install -r requirements.txt
```

Update `config.py` with the directory of the openaddresses repo.

```
# python3 -u -m oa_parcels.parse
```

*Note* - gdal was a pain to install on osx and ubuntu, here are some steps I needed to take.

```
# apt-add-repository ppa:ubuntugis/ubuntugis-unstable
# apt-get update
# pip install --global-option=build_ext --global-option=`gdal-config --cflags` GDAL==`gdal-config --version`
```
