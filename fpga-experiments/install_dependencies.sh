#!/bin/bash

# Update and install general dependencies for Ubuntu-based systems
sudo apt update
sudo apt install -y git build-essential autoconf cmake flex bison \
    libftdi-dev libjson-c-dev libevent-dev libtinfo-dev uml-utilities \
    python3 python3-venv python3-wheel protobuf-compiler libcairo2 \
    libftdi1-2 libftdi1-dev libhidapi-hidraw0 libhidapi-dev libudev-dev \
    pkg-config tree zlib1g-dev zip unzip help2man curl ethtool

# Check if the OS is Ubuntu 22.04 LTS
if [[ "$(lsb_release -rs)" == "22.04" ]]; then
    echo "Ubuntu 22.04 LTS detected, installing additional dependencies..."
    sudo apt install -y libtool libusb-1.0-0-dev
fi

git submodule init
git submodule update --recursive

sudo apt-get install libre2-dev

