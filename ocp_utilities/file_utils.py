import logging
import os


LOGGER = logging.getLogger(__name__)


def write_to_extras_file(extras_file_name, content, extra_dir_name="extras"):
    """
    This will write to a file that will be available after the test execution,

    Args:
        extras_file_name (string): name of the file to write
        content (string): the content of the file to write
        extra_dir_name (string): (optional) the directory name to create inside the test collect dir
    """
    test_dir = collect_logs_prepare_test_dir()
    extras_dir = os.path.join(test_dir, extra_dir_name)
    os.makedirs(extras_dir, exist_ok=True)
    extras_file_path = os.path.join(extras_dir, extras_file_name)
    try:
        with open(extras_file_path, "w") as fd:
            fd.write(content)
    except Exception as exp:
        LOGGER.error(f"Failed to write extras to file: {extras_file_path} {exp}")


def prepare_test_dir_log_utilities():
    """
    Prepares a "utilities" directory under the base log collection directory

    Returns:
        str: TEST_DIR_LOG (the base directory for log collection)
    """
    test_dir_log = os.path.join(
        os.environ.get("TEST_COLLECT_BASE_DIR"),
        "utilities",
    )
    os.environ["TEST_DIR_LOG"] = test_dir_log
    os.makedirs(test_dir_log, exist_ok=True)
    return test_dir_log


def collect_logs_prepare_test_dir():
    """
    Provides and ensures the creation of a directory to collect logs

    If this runs in the scope of a test the directory path structure will include the test node path
    If this is run outside the scope of a test the directory path will be for utilities

    Returns:
        str: test_dir (the directory prefixed for collecting logs)
    """
    test_dir = os.environ.get("TEST_DIR_LOG")
    if not test_dir:
        # log collection was requested outside the scope of a test
        test_dir = prepare_test_dir_log_utilities()
    os.makedirs(test_dir, exist_ok=True)
    return test_dir
