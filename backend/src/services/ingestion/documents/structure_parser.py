from typing import List, Dict, Any, Optional
from loguru import logger
from src.services.ingestion.documents.text_cleaner import clean_element_text

class StructureParser:
    """
    Parses unstructured elements into structured text sections.
    """
    
    @staticmethod
    def parse_elements(elements: List[Any]) -> List[Dict[str, Any]]:
        """
        Group elements into structured sections based on titles.
        
        Args:
            elements: List of unstructured elements
            
        Returns:
            List of section dicts: [{"text": str, "page_number": int}]
        """
        text_sections = []
        current_section = ""
        current_page = None
        
        for el in elements:
            # Clean content
            chunk_content = clean_element_text(el)
            if not chunk_content or not chunk_content.strip():
                continue
            
            # Extract metadata
            meta = getattr(el, "metadata", None) or {}
            if hasattr(meta, "to_dict"):
                meta = meta.to_dict()
            page_num = meta.get("page_number")
            
            # Track page number for first element in section
            if current_page is None:
                current_page = page_num
            
            category = getattr(el, "category", None) if hasattr(el, "category") else None
            
            # Group by sections: Titles start new sections
            if category == "Title":
                # Save previous section if exists
                if current_section.strip():
                    text_sections.append({
                        "text": current_section.strip(),
                        "page_number": current_page,
                    })
                # Start new section
                current_section = chunk_content + "\n\n"
                current_page = page_num
            else:
                # Add category marker for structure awareness
                if category and category not in ["NarrativeText", "UncategorizedText"]:
                    current_section += f"[{category}] {chunk_content}\n\n"
                else:
                    current_section += chunk_content + "\n\n"
        
        # Add final section
        if current_section.strip():
            text_sections.append({
                "text": current_section.strip(),
                "page_number": current_page,
            })
            
        return text_sections

    @staticmethod
    def combine_sections(sections: List[Dict[str, Any]]) -> tuple[str, Optional[int]]:
        """
        Combine sections into a single text block.
        
        Returns:
            Tuple of (full_text, first_page_number)
        """
        if not sections:
            return "", None
            
        full_text = "\n\n---\n\n".join(section["text"] for section in sections)
        first_page = sections[0]["page_number"]
        return full_text, first_page

