"""
Lambda function for compressing search query logs in S3
Triggered by S3 events to compress raw log files for storage optimization
"""
import json
import gzip
import boto3
import os
from typing import Dict, Any
from datetime import datetime
import logging
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch AWS SDK for X-Ray tracing
patch_all()

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
COMPRESSED_PREFIX = os.environ.get('COMPRESSED_PREFIX', 'compressed/')
COMPRESSION_LEVEL = int(os.environ.get('COMPRESSION_LEVEL', '6'))
DELETE_ORIGINAL = os.environ.get('DELETE_ORIGINAL', 'true').lower() == 'true'


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3 event-triggered log compression
    
    Args:
        event: S3 event notification
        context: Lambda context
        
    Returns:
        Response with compression results
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Track metrics
        files_processed = 0
        files_failed = 0
        total_original_size = 0
        total_compressed_size = 0
        
        # Process each S3 record
        for record in event.get('Records', []):
            try:
                # Extract S3 information
                bucket_name = record['s3']['bucket']['name']
                object_key = record['s3']['object']['key']
                
                # Skip if already compressed or in compressed directory
                if object_key.endswith('.gz') or object_key.startswith(COMPRESSED_PREFIX):
                    logger.info(f"Skipping already compressed file: {object_key}")
                    continue
                
                # Skip if not a log file
                if not is_log_file(object_key):
                    logger.info(f"Skipping non-log file: {object_key}")
                    continue
                
                # Compress the file
                result = compress_s3_object(bucket_name, object_key)
                
                if result['success']:
                    files_processed += 1
                    total_original_size += result['original_size']
                    total_compressed_size += result['compressed_size']
                    
                    logger.info(
                        f"Successfully compressed {object_key}: "
                        f"{result['original_size']} -> {result['compressed_size']} bytes "
                        f"({result['compression_ratio']:.2%} reduction)"
                    )
                else:
                    files_failed += 1
                    logger.error(f"Failed to compress {object_key}: {result.get('error')}")
                    
            except Exception as e:
                files_failed += 1
                logger.error(f"Error processing record: {str(e)}", exc_info=True)
        
        # Calculate overall compression ratio
        compression_ratio = 0
        if total_original_size > 0:
            compression_ratio = (total_original_size - total_compressed_size) / total_original_size
        
        # Publish metrics to CloudWatch
        publish_metrics(files_processed, files_failed, total_original_size, 
                       total_compressed_size, compression_ratio)
        
        # Return response
        response = {
            'statusCode': 200,
            'body': json.dumps({
                'files_processed': files_processed,
                'files_failed': files_failed,
                'total_original_size': total_original_size,
                'total_compressed_size': total_compressed_size,
                'compression_ratio': f"{compression_ratio:.2%}",
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
        logger.info(f"Compression completed: {response['body']}")
        return response
        
    except Exception as e:
        logger.error(f"Fatal error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }


def is_log_file(object_key: str) -> bool:
    """
    Check if the object is a log file that should be compressed
    
    Args:
        object_key: S3 object key
        
    Returns:
        True if file should be compressed
    """
    # Check for common log file patterns
    log_extensions = ['.log', '.json', '.txt', '.csv']
    log_patterns = ['logs/', 'raw-data/', 'search-queries/']
    
    # Check extension
    has_log_extension = any(object_key.lower().endswith(ext) for ext in log_extensions)
    
    # Check path pattern
    has_log_pattern = any(pattern in object_key.lower() for pattern in log_patterns)
    
    return has_log_extension or has_log_pattern


def compress_s3_object(bucket_name: str, object_key: str) -> Dict[str, Any]:
    """
    Compress an S3 object using gzip
    
    Args:
        bucket_name: S3 bucket name
        object_key: S3 object key
        
    Returns:
        Dictionary with compression results
    """
    try:
        # Download the object
        logger.info(f"Downloading s3://{bucket_name}/{object_key}")
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        original_data = response['Body'].read()
        original_size = len(original_data)
        
        # Compress the data
        logger.info(f"Compressing {original_size} bytes")
        compressed_data = gzip.compress(original_data, compresslevel=COMPRESSION_LEVEL)
        compressed_size = len(compressed_data)
        
        # Generate compressed object key
        compressed_key = generate_compressed_key(object_key)
        
        # Upload compressed object
        logger.info(f"Uploading compressed file to s3://{bucket_name}/{compressed_key}")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=compressed_key,
            Body=compressed_data,
            ContentType='application/gzip',
            ContentEncoding='gzip',
            Metadata={
                'original-key': object_key,
                'original-size': str(original_size),
                'compressed-size': str(compressed_size),
                'compression-timestamp': datetime.utcnow().isoformat()
            },
            ServerSideEncryption='aws:kms'
        )
        
        # Delete original file if configured
        if DELETE_ORIGINAL:
            logger.info(f"Deleting original file: {object_key}")
            s3_client.delete_object(Bucket=bucket_name, Key=object_key)
        
        # Calculate compression ratio
        compression_ratio = (original_size - compressed_size) / original_size if original_size > 0 else 0
        
        return {
            'success': True,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'compressed_key': compressed_key
        }
        
    except Exception as e:
        logger.error(f"Error compressing object: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def generate_compressed_key(original_key: str) -> str:
    """
    Generate the S3 key for the compressed file
    
    Args:
        original_key: Original S3 object key
        
    Returns:
        Compressed file key
    """
    # Add .gz extension if not present
    if not original_key.endswith('.gz'):
        compressed_key = f"{original_key}.gz"
    else:
        compressed_key = original_key
    
    # Move to compressed prefix if configured
    if COMPRESSED_PREFIX:
        # Extract filename from path
        parts = original_key.split('/')
        filename = parts[-1]
        
        # Preserve date partitioning if present
        date_parts = []
        for part in parts[:-1]:
            if any(prefix in part for prefix in ['year=', 'month=', 'day=', 'hour=']):
                date_parts.append(part)
        
        # Construct new key
        if date_parts:
            compressed_key = f"{COMPRESSED_PREFIX}{'/'.join(date_parts)}/{filename}.gz"
        else:
            compressed_key = f"{COMPRESSED_PREFIX}{filename}.gz"
    
    return compressed_key


def publish_metrics(files_processed: int, files_failed: int, 
                   original_size: int, compressed_size: int, 
                   compression_ratio: float) -> None:
    """
    Publish compression metrics to CloudWatch
    
    Args:
        files_processed: Number of files successfully processed
        files_failed: Number of files that failed
        original_size: Total original size in bytes
        compressed_size: Total compressed size in bytes
        compression_ratio: Overall compression ratio
    """
    try:
        namespace = 'OpenSearchTrendingQueries/Compression'
        timestamp = datetime.utcnow()
        
        metrics = [
            {
                'MetricName': 'FilesProcessed',
                'Value': files_processed,
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'FilesFailed',
                'Value': files_failed,
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'OriginalSize',
                'Value': original_size,
                'Unit': 'Bytes',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'CompressedSize',
                'Value': compressed_size,
                'Unit': 'Bytes',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'CompressionRatio',
                'Value': compression_ratio * 100,
                'Unit': 'Percent',
                'Timestamp': timestamp
            }
        ]
        
        # Publish metrics
        for metric in metrics:
            cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=[metric]
            )
        
        logger.info(f"Published {len(metrics)} metrics to CloudWatch")
        
    except Exception as e:
        logger.error(f"Error publishing metrics: {str(e)}", exc_info=True)
