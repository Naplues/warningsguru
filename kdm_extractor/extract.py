"""
The MIT License (MIT)

Copyright (c) 2016-2017 Louis-Philippe Querel l_querel@encs.concordia.ca

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import re

from util.KDMFileExtractor import extractfile
from util.SourceFilePathGenerator import OriginalFilePathGenerator
from util.FilePathExtractor import FilePathExtractor
from utility.Logging import logger

"""
The purpose of this tool is to extract, transform and load the kdm file generated by the toif assimilitator into the
augmented commitguru as individual, toif view tsv compatible format.
"""


def etl_warnings(kdm_file_path, project_root_directory, repo_id, commit_id, file_mapping):

    # TODO determine if this component can be replaced by the new toif tsv component

    toif_components = extractfile(kdm_file_path)

    # Obtain association of static analysers to warnings
    static_analysers = _extract_static_analysers(toif_components)

    warnings = []
    path_generator = FilePathExtractor(toif_components)
    reverse_engineer_path = OriginalFilePathGenerator(project_root_directory, file_mapping)

    # Identify the files
    for component_id in toif_components:
        component = toif_components[component_id]

        if 'type' in component and component['type'] == "toif:Finding":

            code_location_component = toif_components[component['FindingHasCodeLocation']]

            SFP = toif_components.get(component.get('FindingHasSFPIdentifier')).get('name')
            CWE = toif_components.get(component.get('FindingHasCWEIdentifier')).get('name')
            weakness_description = toif_components.get(component.get('FindingIsDescribedByWeaknessDescription')).get('description')
            line_number = code_location_component.get('lineNumber')

            for static_analyser in static_analysers:
                if component_id in static_analyser.get('related'):
                    static_analyser_name = static_analyser.get('name')

            class_file_path = path_generator.getPath(code_location_component['CodeLocationReferencesFile'])
            relative_file_path = reverse_engineer_path.transform(class_file_path)

            if relative_file_path:
                warnings.append({"repo_id": repo_id, "commit_id": commit_id,  "resource": relative_file_path,
                                 "SFP": SFP, "CWE": CWE, "description": weakness_description,
                                 "line_number": line_number, "generator_tool": static_analyser_name})
            else:
                logger.error("No mapping identified for %s" % class_file_path)

    return warnings


def _extract_static_analysers(toif_components):
    static_analysers = []

    for component_id in toif_components:
        component = toif_components[component_id]

        if 'type' in component and component['type'] == 'toif:TOIFSegment':
            name = toif_components[component.get('TOIFSegmentIsProcessedByAdaptor')].get('name')
            static_analysers.append({'name': name, 'related': component.get('children')})

    return static_analysers
