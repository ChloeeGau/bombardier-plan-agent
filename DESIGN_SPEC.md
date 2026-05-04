# DESIGN_SPEC.md - Bombardier Document Assistant

## Overview
The Bombardier Document Assistant is an AI agent designed to help users (mechanics, engineers, or operators) query airplane plans and user manuals. The agent can answer questions about the content of these documents and, most importantly, extract and display relevant images, figures, and diagrams in the chat response. It also provides links or references to the specific pages in the source documents to ensure traceability and proof.

The agent will leverage Gemini 3's multimodal capabilities to understand both text and visual elements within the PDFs.

## Example Use Cases

### Use Case 1: Visual Identification
*   **User Prompt**: "Show me an image of the brake Wear indicator"
*   **Expected Output**: The agent should display the image/diagram of the brake wear indicator and provide the page number/link to the document where it was found.

### Use Case 2: Location and Instruction
*   **User Prompt**: "Show me on the cockpit, where I can see the brake pressure so that I can turn it on"
*   **Expected Output**: The agent should show the relevant cockpit diagram (e.g., Figure 15-10-9) with a description of where the brake pressure indicator is located and provide helpful text on how to proceed.

### Use Case 3: Procedural Guidance with Visual Aid
*   **User Prompt**: "I want to turn on the parking brake, how do I do it"
*   **Expected Output**: The agent should describe the steps (e.g., "Pull that lever") and display the diagram showing the parking brake lever.

### Use Case 4: Data Extraction from Images
*   **User Prompt**: "I need to change the bracket, give me the dimension of the bracket (length of the bracket)"
*   **Expected Output**: The agent should identify the bracket in the document's diagrams, extract the length dimension from the drawing, display the image, and cite the source page.

## Tools Required
1.  **Document Search/RAG Tool**: To search through the indexed PDFs in Google Cloud Storage.
2.  **Multimodal Retrieval Tool**: To extract specific figures or pages as images based on queries or figure numbers (e.g., "Figure 15-10-9").

## Constraints & Safety Rules
*   **Grounding**: The agent must only use the provided documents to answer questions. If information is missing, it must state that it cannot find it in the manuals.
*   **Accuracy**: Dimensions and procedures must be reported exactly as they appear in the source documents.
*   **No Assumptions**: Do not assume procedures or dimensions not explicitly stated in the text or diagrams.

## Success Criteria
*   **Multimodal Accuracy**: The agent correctly identifies and displays the specific image or diagram requested by the user.
*   **Traceability**: Every answer referencing a document must include the page number or document section.
*   **Helpfulness**: Answers combine text instructions and visual aids effectively.

## Edge Cases to Handle
1.  **Ambiguous Requests**: User asks for a part that appears in multiple places without specifying which one.
2.  **Poor Quality Diagrams**: Handling cases where text in diagrams is difficult to read.
3.  **Missing Figures**: User asks for a specific figure number that does not exist in the documents.
