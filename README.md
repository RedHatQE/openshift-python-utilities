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
```bash
sudo npm install --global release-it
npm install --save-dev @j-ulrich/release-it-regex-bumper
rm -f package.json package-lock.json
```
### usage:
* Create a release, run from the relevant branch.  
To create a 4.11 release, run:
```bash
git checkout v4.11
git pull
release-it # Follow the instructions
```

To enable data-collector pass data-collector.yaml
YAML format:
```yaml
    data_collector_base_directory: "<base directory for data collection>"
    collect_data_function: "<import path for data collection method>"
    collect_pod_logs: true|false # bool whether to collect logs if resource is a pod
```
YAML Example `ocp_utilities/data-collector.yaml`:
```yaml
    data_collector_base_directory: "collected-info"
    collect_data_function: "data_collector.collect_data"
    collect_pod_logs: true
```
Either export path to yaml file in `OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_YAML` or set `data_collector` in your py_config
The environment variable takes precedence over py_config.

To use dynamic base directory, export `OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_DYNAMIC_BASE_DIR`  
Example:
```
data_collector_base_directory = "/data/results/collected-info"
OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_DYNAMIC_BASE_DIR = "dynamic_collector_test_dir"

Result: /data/results/dynamic_collector_test_dir/collected-info
```
