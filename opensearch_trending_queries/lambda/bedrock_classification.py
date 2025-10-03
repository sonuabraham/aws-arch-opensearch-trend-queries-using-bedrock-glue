"""
Lambda function for classifying trending queries using Amazon Bedrock
"""
import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import boto3
from botocore.exceptions import ClientError
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch AWS SDK for X-Ray tracing
patch_all()

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-runtime')

# Environment variables
PROCESSED_DATA_BUCKET = os.environ['PROCESSED_DATA_BUCKET']
RESULTS_TABLE_NAME = os.environ['RESULTS_TABLE_NAME']
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
RETRY_DELAY = int(os.environ.get('RETRY_DELAY', 2))

# DynamoDB table
results_table = dynamodb.Table(RESULTS_TABLE_NAME)


def handler(event, context):
    """
    Lambda handler for classifying trending queries using Bedrock
    
    Args:
        event: Lambda event containing date or cluster information
        context: Lambda context
        
    Returns:
        Response with classification results
    """
    try:
        logger.info(f"Starting Bedrock classification with event: {json.dumps(event)}")
        
        # Get date from event or use yesterday
        xray_recorder.begin_subsegment('parse_event')
        target_date = event.get('date')
        if not target_date:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        xray_recorder.put_annotation('target_date', target_date)
        xray_recorder.end_subsegment()
        
        logger.info(f"Processing trending queries for date: {target_date}")
        
        # Read clustered queries from S3
        xray_recorder.begin_subsegment('read_s3_data')
        clustered_queries = read_clustered_queries(target_date)
        xray_recorder.put_metadata('queries_count', len(clustered_queries))
        xray_recorder.end_subsegment()
        
        if not clustered_queries:
            logger.warning(f"No clustered queries found for date: {target_date}")
            return {
                'statusCode': 404,
                'body': json.dumps({'message': 'No clustered queries found'})
            }
        
        logger.info(f"Found {len(clustered_queries)} clustered queries")
        
        # Get top queries by cluster
        xray_recorder.begin_subsegment('group_by_cluster')
        top_queries_by_cluster = get_top_queries_by_cluster(clustered_queries)
        xray_recorder.put_metadata('cluster_count', len(top_queries_by_cluster))
        xray_recorder.end_subsegment()
        
        # Classify queries using Bedrock
        xray_recorder.begin_subsegment('bedrock_classification')
        classified_queries = classify_queries_with_bedrock(top_queries_by_cluster)
        xray_recorder.put_metadata('classified_count', len(classified_queries))
        xray_recorder.end_subsegment()
        
        # Calculate trending metrics
        xray_recorder.begin_subsegment('calculate_metrics')
        trending_queries = calculate_trending_metrics(classified_queries)
        xray_recorder.end_subsegment()
        
        # Store results in DynamoDB
        xray_recorder.begin_subsegment('store_results')
        store_results(target_date, trending_queries)
        xray_recorder.end_subsegment()
        
        logger.info(f"Successfully classified and stored {len(trending_queries)} trending queries")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Classification completed successfully',
                'date': target_date,
                'trending_queries_count': len(trending_queries)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in Bedrock classification: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def read_clustered_queries(date: str) -> List[Dict[str, Any]]:
    """
    Read clustered queries from S3 for a specific date
    
    Args:
        date: Date string in YYYY-MM-DD format
        
    Returns:
        List of clustered query records
    """
    try:
        # Parse date for partitioning
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # Construct S3 path with date partition
        s3_prefix = f"clustered-queries/date={date}/"
        
        logger.info(f"Reading from S3: s3://{PROCESSED_DATA_BUCKET}/{s3_prefix}")
        
        # List objects in the partition
        response = s3_client.list_objects_v2(
            Bucket=PROCESSED_DATA_BUCKET,
            Prefix=s3_prefix
        )
        
        if 'Contents' not in response:
            logger.warning(f"No objects found at {s3_prefix}")
            return []
        
        # For simplicity, read the first parquet file
        # In production, you might want to use AWS Data Wrangler or similar
        queries = []
        
        # Note: This is a simplified version. In production, use aws-data-wrangler
        # or read parquet files properly. For now, we'll simulate the data structure
        logger.info(f"Found {len(response['Contents'])} files in partition")
        
        # Return empty list for now - in production, parse parquet files
        # This would typically use pyarrow or aws-data-wrangler
        return queries
        
    except ClientError as e:
        logger.error(f"S3 error reading clustered queries: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error reading clustered queries: {str(e)}")
        raise


def get_top_queries_by_cluster(queries: List[Dict[str, Any]], top_n: int = 5) -> Dict[int, List[Dict[str, Any]]]:
    """
    Get top N queries for each cluster
    
    Args:
        queries: List of query records
        top_n: Number of top queries per cluster
        
    Returns:
        Dictionary mapping cluster_id to top queries
    """
    from collections import defaultdict
    
    cluster_queries = defaultdict(list)
    
    # Group queries by cluster
    for query in queries:
        cluster_id = query.get('cluster_id', 0)
        cluster_queries[cluster_id].append(query)
    
    # Sort and get top N for each cluster
    top_queries = {}
    for cluster_id, cluster_list in cluster_queries.items():
        sorted_queries = sorted(
            cluster_list,
            key=lambda x: x.get('query_count', 0),
            reverse=True
        )
        top_queries[cluster_id] = sorted_queries[:top_n]
    
    return top_queries


def classify_queries_with_bedrock(queries_by_cluster: Dict[int, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Classify queries using Amazon Bedrock LLM
    
    Args:
        queries_by_cluster: Dictionary of queries grouped by cluster
        
    Returns:
        List of classified queries with categories
    """
    classified_queries = []
    
    for cluster_id, queries in queries_by_cluster.items():
        logger.info(f"Classifying cluster {cluster_id} with {len(queries)} queries")
        
        # Extract query texts
        query_texts = [q.get('query_text', '') for q in queries]
        
        # Classify the cluster
        category = classify_cluster_with_retry(query_texts, cluster_id)
        
        # Add category to each query
        for query in queries:
            query['category'] = category
            query['cluster_id'] = cluster_id
            classified_queries.append(query)
    
    return classified_queries


def classify_cluster_with_retry(query_texts: List[str], cluster_id: int) -> str:
    """
    Classify a cluster of queries with retry logic
    
    Args:
        query_texts: List of query text strings
        cluster_id: Cluster identifier
        
    Returns:
        Category string
    """
    for attempt in range(MAX_RETRIES):
        try:
            return invoke_bedrock_for_classification(query_texts, cluster_id)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            
            if error_code == 'ThrottlingException' and attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Throttled by Bedrock API, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                logger.error(f"Bedrock API error: {str(e)}")
                return "uncategorized"
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return "uncategorized"
    
    return "uncategorized"


def invoke_bedrock_for_classification(query_texts: List[str], cluster_id: int) -> str:
    """
    Invoke Bedrock model for query classification
    
    Args:
        query_texts: List of query text strings
        cluster_id: Cluster identifier
        
    Returns:
        Category string
    """
    # Create prompt for classification
    queries_str = "\n".join([f"- {q}" for q in query_texts[:10]])  # Limit to 10 queries
    
    prompt = f"""Analyze the following search queries and classify them into a single category.
Choose from these categories: education, entertainment, technology, shopping, health, news, travel, finance, sports, other.

Search queries:
{queries_str}

Respond with only the category name, nothing else."""

    # Prepare request body based on model
    if "anthropic.claude" in BEDROCK_MODEL_ID:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1
        }
    elif "amazon.titan" in BEDROCK_MODEL_ID:
        request_body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 50,
                "temperature": 0.1,
                "topP": 0.9
            }
        }
    else:
        # Default format
        request_body = {
            "prompt": prompt,
            "max_tokens": 50,
            "temperature": 0.1
        }
    
    logger.info(f"Invoking Bedrock model: {BEDROCK_MODEL_ID}")
    
    # Invoke Bedrock
    response = bedrock_runtime.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(request_body)
    )
    
    # Parse response
    response_body = json.loads(response['body'].read())
    
    # Extract category based on model response format
    if "anthropic.claude" in BEDROCK_MODEL_ID:
        category = response_body.get('content', [{}])[0].get('text', 'other').strip().lower()
    elif "amazon.titan" in BEDROCK_MODEL_ID:
        results = response_body.get('results', [{}])
        category = results[0].get('outputText', 'other').strip().lower() if results else 'other'
    else:
        category = response_body.get('completion', 'other').strip().lower()
    
    logger.info(f"Cluster {cluster_id} classified as: {category}")
    
    return category


def calculate_trending_metrics(queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calculate trending metrics for queries
    
    Args:
        queries: List of classified queries
        
    Returns:
        List of trending queries with metrics
    """
    # Sort by query count
    sorted_queries = sorted(
        queries,
        key=lambda x: x.get('query_count', 0),
        reverse=True
    )
    
    # Add rank and format for output
    trending_queries = []
    for rank, query in enumerate(sorted_queries[:50], start=1):  # Top 50
        trending_query = {
            'query': query.get('query_text', ''),
            'rank': rank,
            'count': query.get('query_count', 0),
            'unique_users': query.get('unique_users', 0),
            'category': query.get('category', 'other'),
            'cluster_id': query.get('cluster_id', 0),
            'click_through_rate': round(query.get('click_through_rate', 0), 3)
        }
        
        # Calculate growth rate if available (placeholder for now)
        trending_query['growth_rate'] = 0.0
        
        trending_queries.append(trending_query)
    
    return trending_queries


def store_results(date: str, trending_queries: List[Dict[str, Any]]) -> None:
    """
    Store trending query results in DynamoDB
    
    Args:
        date: Date string
        trending_queries: List of trending queries
    """
    try:
        # Calculate TTL (30 days from now)
        ttl = int((datetime.now() + timedelta(days=30)).timestamp())
        
        # Store in DynamoDB
        item = {
            'date': date,
            'trending_queries': trending_queries,
            'ttl': ttl,
            'processed_at': datetime.now().isoformat(),
            'query_count': len(trending_queries)
        }
        
        results_table.put_item(Item=item)
        
        logger.info(f"Stored {len(trending_queries)} trending queries for date {date}")
        
    except ClientError as e:
        logger.error(f"DynamoDB error storing results: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error storing results: {str(e)}")
        raise
