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
import logging
import os
from typing import Any

import vertexai
from dotenv import load_dotenv
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.cloud import logging as google_cloud_logging
from vertexai.agent_engines.templates.adk import AdkApp

from app.agent import app as adk_app
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Load environment variables from .env file at runtime
load_dotenv()

class CustomGcsArtifactService(GcsArtifactService):
    def _get_artifact_version_sync(
        self,
        app_name,
        user_id,
        session_id,
        filename,
        version=None,
    ):
        if version is None:
            versions = self._list_versions(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                filename=filename,
            )
            if not versions:
                return None
            version = max(versions)

        blob_name = self._get_blob_name(
            app_name, user_id, filename, version, session_id
        )
        # Use projection="noAcl" to avoid error on uniform bucket access!
        blob = self.bucket.get_blob(blob_name, projection="noAcl")

        if not blob:
            return None

        from google.adk.artifacts.base_artifact_service import ArtifactVersion
        canonical_uri = f"gs://{self.bucket_name}/{blob.name}"

        return ArtifactVersion(
            version=version,
            canonical_uri=canonical_uri,
            create_time=blob.time_created.timestamp(),
            mime_type=blob.content_type,
            custom_metadata=blob.metadata if blob.metadata else {},
        )

class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the agent engine app with logging and telemetry."""
        vertexai.init()
        setup_telemetry()
        super().set_up()
        logging.basicConfig(level=logging.INFO)
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    async def _convert_response_events(
        self,
        user_id,
        session_id,
        events,
        artifact_service,
    ):
        """Intercepts response to attach artifact as a Part for Gemini Enterprise."""
        response_dict = await super()._convert_response_events(
            user_id, session_id, events, artifact_service
        )
        
        artifacts = response_dict.get("artifacts", [])
        if not artifacts:
            return response_dict
            
        # Get the latest version of the first artifact
        artifact = artifacts[0]
        versions = artifact.get("versions", [])
        if not versions:
            return response_dict
            
        latest_version = versions[-1]
        img_part = latest_version.get("data")
        
        if not img_part:
            return response_dict
            
        # Find the last event and try to attach the part
        resp_events = response_dict.get("events", [])
        for event in reversed(resp_events):
            # Look for content with parts (standard message structure)
            content = event.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    parts.append(img_part)
                    logging.info("Successfully attached artifact as Part to final response.")
                    break
                    
        return response_dict

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()
        operations[""] = operations.get("", []) + ["register_feedback"]
        return operations


gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
agent_engine = AgentEngineApp(
    app=adk_app,
    artifact_service_builder=lambda: CustomGcsArtifactService(bucket_name=logs_bucket_name),
)
