# openshift-python-utilities
Pypi: [openshift-python-utilities](https://pypi.org/project/openshift-python-utilities/)  
A utilities repository for [openshift-restclient-python](https://github.com/openshift/openshift-restclient-python)

## Release new version
### requirements:
* Export GitHub token
```bash
export GITHUB_TOKEN=<your_github_token>
```
* [release-it](https://github.com/release-it/release-it)

Run the following once (execute outside repository dir for example `~/`):
```bash
sudo npm install --global release-it
npm install --save-dev @release-it/bumper
```
### usage:
* Create a release, run from the relevant branch.  
To create a 4.11 release, run:
```bash
git checkout v4.11
git pull
release-it # Follow the instructions
```
