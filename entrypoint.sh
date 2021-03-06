#!/bin/bash

set -ex
rc=0

export GITHUB_TOKEN=$1
export TAG_IN_ISSUES=$2
export MODULES_REPO=$3
export COMPARISON_LEVEL=$4
export TEST_AGAIN=$5
export FORCE_RECHECK_PR=$6

echo 'TAG_IN_ISSUES = ' $TAG_IN_ISSUES
echo 'MODULES_REPO = ' $MODULES_REPO
echo 'COMPARISON_LEVEL = ' $COMPARISON_LEVEL
echo 'TEST_AGAIN = ' $TEST_AGAIN
echo 'FORCE_RECHECK_PR = ' $FORCE_RECHECK_PR

apt-get update -y
apt-get install python3.7 git python3-distutils -y
echo `which python3.7`
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.7
echo `which pip3`
echo `pwd`
echo `ls -la`
python3.7 -m pip install --upgrade setuptools
python3.7 -m pip install wheel --user
python3.7 -m pip install gitpython~=3.1 ruamel.yaml==0.16.12 PyGithub==1.53 semver==2.13.0 --user
git clone --depth=1 https://$GITHUB_TOKEN@github.com/$MODULES_REPO hub_repo
python3.7 /hub_updater.py
