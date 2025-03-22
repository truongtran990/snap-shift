"""
Batch configuration for file transfers
"""

class BatchConfig:
    """Configuration for batch transfers"""
    # Maximum size of a single batch (2GB by default)
    MAX_BATCH_SIZE = 2 * 1024 * 1024 * 1024  # Convert GB to bytes
    
    # Maximum number of files in a single batch
    MAX_FILES_PER_BATCH = 50
    
    # Delay between batches in seconds
    BATCH_DELAY = 1.0 