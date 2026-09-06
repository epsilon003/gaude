"""
Language-aware chunking for source code and docs.
Uses tree-sitter for AST-aware chunking where possible, falling back to 
LangChain's RecursiveCharacterTextSplitter.from_language() for unsupported languages.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

EXTENSION_LANGUAGE_MAP: dict[str, Language] = {
    ".py": Language.PYTHON, ".js": Language.JS, ".jsx": Language.JS, ".mjs": Language.JS,
    ".ts": Language.TS, ".tsx": Language.TS, ".java": Language.JAVA, ".go": Language.GO,
    ".rb": Language.RUBY, ".php": Language.PHP, ".cpp": Language.CPP, ".cc": Language.CPP,
    ".cxx": Language.CPP, ".c": Language.CPP, ".h": Language.CPP, ".hpp": Language.CPP,
    ".cs": Language.CSHARP, ".rs": Language.RUST, ".kt": Language.KOTLIN, ".kts": Language.KOTLIN,
    ".scala": Language.SCALA, ".swift": Language.SWIFT, ".md": Language.MARKDOWN,
    ".markdown": Language.MARKDOWN, ".rst": Language.RST, ".html": Language.HTML,
    ".htm": Language.HTML, ".sol": Language.SOL,
}

INGESTIBLE_EXTENSIONS = set(EXTENSION_LANGUAGE_MAP.keys()) | {
    ".txt", ".yaml", ".yml", ".json", ".sql", ".sh", ".toml", ".cfg", ".ini",
}

IGNORED_DIR_NAMES = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".next", "vendor", "target", ".idea", ".vscode", "coverage", ".pytest_cache",
}

IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock",
    "Gemfile.lock", "go.sum", "mix.lock",
}

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150
MAX_FILE_SIZE_BYTES = 500_000

@dataclass
class CodeChunk:
    text: str
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)

def should_ingest_file(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in IGNORED_DIR_NAMES for p in parts): return False
    if parts[-1] in IGNORED_FILENAMES: return False
    ext = os.path.splitext(path)[1].lower()
    return ext in INGESTIBLE_EXTENSIONS

def get_splitter_for_file(file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    ext = os.path.splitext(file_path)[1].lower()
    lang = EXTENSION_LANGUAGE_MAP.get(ext)
    if lang is not None:
        return RecursiveCharacterTextSplitter.from_language(language=lang, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", " ", ""])

# --- Tree-sitter AST Chunking (Item 3) ---
try:
    from tree_sitter_language_pack import get_parser, get_language
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

TS_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".java": "java", ".go": "go", ".rb": "ruby",
    ".php": "php", ".cpp": "cpp", ".c": "c", ".h": "c", ".rs": "rust", ".cs": "c_sharp",
}

def _chunk_with_tree_sitter(file_path: str, content: str) -> list[str] | None:
    if not TREE_SITTER_AVAILABLE: return None
    ext = os.path.splitext(file_path)[1].lower()
    lang_name = TS_LANG_MAP.get(ext)
    if not lang_name: return None
    
    try:
        parser = get_parser(lang_name)
        tree = parser.parse(content.encode('utf-8'))
        
        node_types_to_extract = {
            "python": ["function_definition", "class_definition"],
            "javascript": ["function_declaration", "class_declaration", "arrow_function", "method_definition"],
            "typescript": ["function_declaration", "class_declaration", "arrow_function", "method_definition", "interface_declaration", "type_alias_declaration"],
            "tsx": ["function_declaration", "class_declaration", "arrow_function", "method_definition", "interface_declaration", "type_alias_declaration"],
            "java": ["class_declaration", "method_declaration", "interface_declaration"],
            "go": ["function_declaration", "method_declaration", "type_declaration"],
            "ruby": ["method", "class", "module"],
            "php": ["function_definition", "class_declaration", "method_declaration"],
            "cpp": ["function_definition", "class_specifier", "namespace_definition"],
            "c": ["function_definition", "struct_specifier"],
            "rust": ["function_item", "impl_item", "struct_item", "trait_item"],
            "c_sharp": ["class_declaration", "method_declaration", "interface_declaration"],
        }
        
        target_types = node_types_to_extract.get(lang_name, [])
        if not target_types: return None
        
        chunks = []
        def traverse(node):
            if node.type in target_types:
                chunks.append(content[node.start_byte:node.end_byte])
                return # Don't traverse children to avoid nested duplicates
            for child in node.children:
                traverse(child)
                
        traverse(tree.root_node)
        return chunks if chunks else None
    except Exception:
        return None

def chunk_file(file_path: str, content: str, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[CodeChunk]:
    if not content.strip(): return []
    
    ext = os.path.splitext(file_path)[1].lower()
    lang = EXTENSION_LANGUAGE_MAP.get(ext)
    lang_name = lang.value if lang is not None else "text"
    
    # 1. Try AST-based chunking
    raw_chunks = _chunk_with_tree_sitter(file_path, content)
    
    # 2. Fallback to LangChain if AST failed or yielded nothing
    if not raw_chunks:
        splitter = get_splitter_for_file(file_path, chunk_size, chunk_overlap)
        raw_chunks = splitter.split_text(content)
        
    # 3. Resolve line numbers
    results: list[CodeChunk] = []
    search_from = 0
    for chunk_text in raw_chunks:
        idx = content.find(chunk_text, search_from)
        if idx == -1: idx = content.find(chunk_text)
        
        if idx == -1:
            start_line, end_line = None, None
        else:
            start_line = content.count("\n", 0, idx) + 1
            end_line = start_line + chunk_text.count("\n")
            search_from = idx + max(1, len(chunk_text) - chunk_overlap)
            
        results.append(CodeChunk(
            text=chunk_text, file_path=file_path, 
            start_line=start_line, end_line=end_line, language=lang_name
        ))
    return results