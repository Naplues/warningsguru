"""
The purpose of this script is to automatically run the TOIF adaptors on each commit that commitguru as analysed.
"""
import subprocess
import time
from time import sleep
import os

from db_versioning import flyway_runner
from pom_injector.update_pom import update_pom
from kdm_extractor import extract
from repos.repo_manager import load_repository
from utility.Logging import logger
from utility.service_sql import *

import config
from config import *

BUILD = "BUILD"
PROJECT_NAME = "StaticGuru"
VERSION = "0.0.1"


class AdaptorRunner:

    def __init__(self):
        logger.info("Starting %s - version %s" % (PROJECT_NAME, VERSION))

        # TODO check dependencies for all modules (toif, git, commitguru, maven, etc.)

        db = config.get_local_settings()

        # Checking the state of database and attempting to migrate if necessary
        flyway_runner.migrate_db(db[DATABASE_HOST], db[DATABASE_PORT], db[DATABASE_NAME], db[DATABASE_USERNAME], db[DATABASE_PASSWORD])

        # Once everything as been validated we can start the service
        logger.info("Service prerequisites check complete. Starting %s" % PROJECT_NAME)
        self._start_service()


    def _start_service(self):

        service_db = Service_DB(REPROCESS_FAILURES_HOURS)

        service_db.setup_tables_in_commit_guru()

        while True:
            print "test"
            commits = service_db.get_unprocessed_commits()

            if len(commits) > 0:

                service_db.truncate_commit_processing()
                service_db.queued_commit(commits)

                # Checkout repo to commit
                for commit in commits:
                    repo_id = commit['repo']
                    commit_hash = commit['commit']

                    service_db.processing_commit(repo_id, commit_hash)
                    load_repository(repo_id)
                    repo_dir = os.path.join(config.REPOSITORY_CACHE_PATH, repo_id)

                    mvn_result, log = process_inject_run_commit(commit, repo_dir)

                    if mvn_result == BUILD:
                        # Build was successful so we can continue
                        log = "\n".join((log, run_assimilator(repo_dir)))

                        kdm_file = _get_kdm_file_output_path(repo_dir)
                        zip_kdm_file = kdm_file + ".zip"

                        if os.path.isfile(zip_kdm_file):

                            _extract_kdm_file(repo_dir)

                            if os.path.isfile(kdm_file):

                                # Process extracted kdm file
                                warnings = extract.etl_warnings(_get_kdm_file_output_path(repo_dir), repo_dir, commit['repo'], commit['commit'])

                                # Save warnings to db
                                service_db.add_commit_warning_lines(warnings)

                            else:
                                log = "\n".join((log, "file %s does not exist. this is not normal as zip file existed"
                                                % kdm_file))
                                mvn_result = "TOOL ERROR"


                        else:
                            log = "\n".join((log, "file %s does not exist. This could be normal as it is possible that"
                                                 " no files were run" % zip_kdm_file))

                    service_db.processed_commit(commit['repo'], commit['commit'], mvn_result, log=log)

            else:
                print "No new tasks to run. Going to sleep for %s minutes" % BACKGROUND_SLEEP_MINUTES
                time.sleep(BACKGROUND_SLEEP_MINUTES*60)



    """
    1. get commits from commitguru that have not been ran by adaptor yet
    2. Prepare maven pom file
    """

    """
    -- static process commit table
    repo commit status build date

    -- static file warnings
    repo commit
    """

runner_base_dir_path = os.path.abspath(os.path.join(os.path.curdir, 'maven_toif_runner'))


def process_inject_run_commit(commit, repo_dir):

    print("Checking out %s from %s" % (commit['commit'], os.getcwd()))
    subprocess.call("git reset --hard; git clean -df; git checkout %s" % commit['commit'], shell=True, cwd=repo_dir)

    # Check if it's a maven project
    pom_file_path = os.path.join(repo_dir, "pom.xml")
    pom_exists = os.path.exists(pom_file_path)

    if pom_exists:

        adaptor_dir_path = _get_adaptor_output_dir_path(repo_dir)
        update_pom(pom_file_path, runner_base_dir_path, repo_dir, adaptor_dir_path)


        mvn_cleaning = subprocess.Popen("mvn clean:clean", shell=True, cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Create directory where to save toif adaptor files
        if not os.path.exists(adaptor_dir_path):
            os.makedirs(adaptor_dir_path)

        print("Building %s and running TOIF adaptors" % commit['commit'])
        process = subprocess.Popen("mvn package -DskipTests", shell=True, cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        maven_logs = process.communicate()[0]
        # todo log the results
        if process.returncode == 0:
            print("Build Success")
            return BUILD, maven_logs
        else:
            print("Build Failed")
            return "FAILURE", maven_logs

    else:
        print("Missing POM - Nothing to build")
        return "MISSING POM", ""


def _get_adaptor_output_dir_path(repo_dir):
    return os.path.join(repo_dir, ADAPTOR_OUTPUT_DIR)


def _get_kdm_file_output_path(repo_dir):
    # TODO make this configurable
    return os.path.abspath(os.path.join(repo_dir, KDM_FILE))


def run_assimilator(repo_dir):
    adaptor_output_path = os.path.abspath(_get_adaptor_output_dir_path(repo_dir))
    assimilator_output_file_path = _get_kdm_file_output_path(repo_dir)
    # assimilator_output_file_path = "/home/louisq/test.kdm"
    assimilator_process = subprocess.Popen("%s --merge --kdmfile=%s --inputfile=%s" %
                                           (TOIF_EXECUTABLE, assimilator_output_file_path, adaptor_output_path),
                                           shell=True, cwd=os.path.abspath(repo_dir), stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT)

    # return the assimilator log results
    sleep(20)
    return assimilator_process.communicate()[0]


def _extract_kdm_file(repo_dir):

    assimilator_output_file_path = _get_kdm_file_output_path(repo_dir)

    # TODO remove when toif is fixed and does not create two copies of the file: {name} and {name}.zip. File {name} is empty
    process = subprocess.Popen("rm %s; unzip %s" % (assimilator_output_file_path, assimilator_output_file_path + ".zip"),
                     shell=True, cwd=os.path.abspath(repo_dir), stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT)
    process.communicate()[0]
    sleep(5)

AdaptorRunner()
