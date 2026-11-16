"""Thai & Multilingual Tokenization Module for SQLite FTS5 Indexing.
Uses PyThaiNLP for accurate offline dictionary-based segmentation (newmm).
100% offline, free, and local.
"""

import re
import logging

logger = logging.getLogger(__name__)

try:
    from pythainlp.tokenize import word_tokenize
    PYTHAINLP_AVAILABLE = True
except ImportError:
    PYTHAINLP_AVAILABLE = False
    logger.warning("PyThaiNLP not available. Falling back to basic regex tokenization.")


def tokenize_for_fts(text: str) -> str:
    """Tokenize Thai and English text by inserting spaces between Thai words.
    
    This allows SQLite FTS5 (unicode61 tokenizer) to index individual Thai words
    despite Thai not having spaces between words in natural text.
    
    Args:
        text: Raw string in Thai, English, or mixed.
        
    Returns:
        Space-separated tokenized text suitable for FTS5 indexing.
    """
    if not text:
        return ""

    # Clean redundant whitespace and control characters
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return ""

    if PYTHAINLP_AVAILABLE:
        try:
            tokens = word_tokenize(text, engine="newmm", keep_whitespace=False)
            # Filter empty or pure whitespace tokens
            clean_tokens = [t.strip() for t in tokens if t.strip()]
            return " ".join(clean_tokens)
        except Exception as e:
            logger.error(f"Error in PyThaiNLP tokenization: {e}")

    # Fallback if pythainlp fails or is absent: split by spaces and basic punctuation
    return " ".join(re.findall(r'[\w\u0E00-\u0E7F]+', text))


def prepare_search_query(query: str) -> str:
    """Prepares user input search query for SQLite FTS5.
    
    Splits into words using the same Thai tokenizer, escapes special FTS5
    characters, and formats for Boolean AND search.
    
    Args:
        query: Raw search query typed by user.
        
    Returns:
        FTS5 MATCH formatted query string.
    """
    if not query:
        return ""

    # Remove dangerous FTS5 syntax chars like quotes, asterisks, brackets if not structured
    clean_query = re.sub(r'["\'\*\^\:\(\)\{\}\[\]]', ' ', query)
    tokenized = tokenize_for_fts(clean_query)
    tokens = tokenized.split()

    if not tokens:
        return ""

    # Wrap each token in double quotes to avoid FTS5 syntax errors and match exact tokens
    escaped_tokens = [f'"{token}"' for token in tokens if token]
    
    # By default, use AND logic so all query tokens must match
    return " AND ".join(escaped_tokens)
