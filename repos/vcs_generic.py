"""
In order to allow static guru to work with many different version control system this should be the base to
"""


class VCS(object):

    # TODO add capability to checkout

    """
    Expected response
    """
    def get_warning_blames(self, repo_path, relative_file_path, warnings):
        raise NotImplementedError("Class %s doesn't implement get_warning_blames()" % (self.__class__.__name__))