sudo apt-get update -y
sudo apt-get install python3.7 git python3-distutils python3-pip python3-setuptools -y
echo `which python3.7`
echo `which pip3`
python3.7 -m pip install wheel --user
python3.7 -m pip install -r requirements.txt --user
git clone --depth=1 https://$GITHUB_TOKEN@github.com/$MODULES_REPO hub_repo
