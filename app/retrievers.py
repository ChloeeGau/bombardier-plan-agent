# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from collections.abc import Callable
import google.auth
from googleapiclient import discovery

def create_search_tool(data_store_path: str) -> Callable[[str], str]:
    """Create a custom Vertex AI Search tool."""
    
    def search_tool(query: str) -> str:
        """Search the Bombardier documents for information."""
        credentials, project_id = google.auth.default()
        credentials = credentials.with_quota_project(project_id)
        
        # Extract location and data_store_id from path
        parts = data_store_path.split("/")
        location = parts[3]
        data_store_id = parts[-1]
        
        if location == "global":
            endpoint = "https://discoveryengine.googleapis.com"
        else:
            endpoint = f"https://{location}-discoveryengine.googleapis.com"
            
        service = discovery.build(
            "discoveryengine",
            "v1alpha",
            credentials=credentials,
            discoveryServiceUrl=f"{endpoint}/$discovery/rest?version=v1alpha",
        )
        
        serving_config = f"projects/{project_id}/locations/{location}/collections/default_collection/dataStores/{data_store_id}/servingConfigs/default_serving_config"
        
        try:
            request = service.projects().locations().collections().dataStores().servingConfigs().search(
                servingConfig=serving_config,
                body={"query": query}
            )
            response = request.execute()
            
            results = response.get("results", [])
            snippets = []
            for result in results:
                document = result.get("document", {})
                derived_data = document.get("derivedStructData", {})
                snippets_list = derived_data.get("snippets", [])
                for s in snippets_list:
                    snippets.append(s.get("snippet", ""))
                    
            return "\n".join(snippets) if snippets else "No results found."
        except Exception as e:
            return f"Error during search: {e}"

    # For integration tests, return a mock function instead of the real tool
    if os.getenv("INTEGRATION_TEST") == "TRUE":
        def mock_search(query: str) -> str:
            """Mock Vertex AI Search for integration tests."""
            return "Mock search result for testing purposes."
        return mock_search

    return search_tool
