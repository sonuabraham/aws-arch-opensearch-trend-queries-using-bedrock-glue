"""
Lambda function for GET /trending-queries endpoint
Retrieves current trending queries from DynamoDB
"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch AWS SDK for X-Ray tracing
patch_all()

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("TABLE_NAME")
table = dynamodb.Table(table_name)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for GET /trending-queries endpoint
    
    Query Parameters:
        - limit (optional): Maximum number of results to return (default: 50, max: 100)
        - next_token (optional): Pagination token for retrieving next page
    
    Returns:
        JSON response with trending queries for the current date
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Add custom X-Ray metadata
        xray_recorder.begin_subsegment('parse_parameters')
        # Parse query parameters
        limit = _parse_limit(event)
        next_token = _parse_next_token(event)
        xray_recorder.put_metadata('limit', limit)
        xray_recorder.end_subsegment()
        
        # Get current date in YYYY-MM-DD format
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        xray_recorder.put_annotation('query_date', current_date)
        
        logger.info(f"Querying trending queries for date: {current_date}, limit: {limit}")
        
        # Query DynamoDB for trending queries
        xray_recorder.begin_subsegment('query_dynamodb')
        response = _query_trending_queries(current_date, limit, next_token)
        xray_recorder.put_metadata('items_returned', len(response.get('Items', [])))
        xray_recorder.end_subsegment()
        
        # Format response
        xray_recorder.begin_subsegment('format_response')
        formatted_response = _format_response(response, current_date)
        xray_recorder.end_subsegment()
        
        logger.info(f"Successfully retrieved {len(formatted_response['trending_queries'])} trending queries")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(formatted_response)
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "error": "BadRequest",
                "message": f"[BadRequest] {str(e)}"
            })
        }
    
    except ClientError as e:
        logger.error(f"DynamoDB error: {str(e)}")
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        
        if error_code == "ResourceNotFoundException":
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "error": "NotFound",
                    "message": "[NotFound] Trending queries table not found"
                })
            }
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "error": "InternalError",
                "message": "[InternalError] Failed to retrieve trending queries"
            })
        }
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "error": "InternalError",
                "message": "[InternalError] An unexpected error occurred"
            })
        }


def _parse_limit(event: Dict[str, Any]) -> int:
    """
    Parse and validate the limit query parameter
    
    Args:
        event: Lambda event object
    
    Returns:
        Validated limit value (default: 50, max: 100)
    
    Raises:
        ValueError: If limit is invalid
    """
    limit_str = event.get("limit") or event.get("queryStringParameters", {}).get("limit", "50")
    
    try:
        limit = int(limit_str)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid limit parameter: {limit_str}. Must be an integer.")
    
    if limit < 1:
        raise ValueError(f"Invalid limit parameter: {limit}. Must be greater than 0.")
    
    if limit > 100:
        raise ValueError(f"Invalid limit parameter: {limit}. Maximum allowed is 100.")
    
    return limit


def _parse_next_token(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse and validate the next_token query parameter
    
    Args:
        event: Lambda event object
    
    Returns:
        Decoded next_token or None
    
    Raises:
        ValueError: If next_token is invalid
    """
    next_token_str = event.get("next_token") or event.get("queryStringParameters", {}).get("next_token")
    
    if not next_token_str:
        return None
    
    try:
        # Decode base64 encoded pagination token
        import base64
        decoded = base64.b64decode(next_token_str).decode("utf-8")
        next_token = json.loads(decoded)
        return next_token
    except Exception as e:
        raise ValueError(f"Invalid next_token parameter: {str(e)}")


def _query_trending_queries(
    date: str,
    limit: int,
    next_token: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Query DynamoDB for trending queries
    
    Args:
        date: Date in YYYY-MM-DD format
        limit: Maximum number of results
        next_token: Pagination token
    
    Returns:
        DynamoDB query response
    """
    query_params = {
        "KeyConditionExpression": Key("date").eq(date),
        "Limit": limit,
        "ScanIndexForward": True  # Sort by sort key (query_id) in ascending order
    }
    
    if next_token:
        query_params["ExclusiveStartKey"] = next_token
    
    response = table.query(**query_params)
    
    return response


def _format_response(
    dynamodb_response: Dict[str, Any],
    date: str
) -> Dict[str, Any]:
    """
    Format DynamoDB response into API response format
    
    Args:
        dynamodb_response: Raw DynamoDB query response
        date: Query date
    
    Returns:
        Formatted API response
    """
    items = dynamodb_response.get("Items", [])
    
    # Extract trending queries from items
    trending_queries = []
    for item in items:
        # Parse the query data from the item
        # The item structure depends on how data is stored in DynamoDB
        # Assuming the structure matches the design document
        query_data = {
            "query": item.get("query_text", item.get("query", "")),
            "rank": int(item.get("rank", 0)),
            "count": int(item.get("count", 0))
        }
        
        # Add optional fields if present
        if "growth_rate" in item:
            query_data["growth_rate"] = float(item["growth_rate"])
        
        if "category" in item:
            query_data["category"] = item["category"]
        
        if "cluster_id" in item:
            query_data["cluster_id"] = item["cluster_id"]
        
        trending_queries.append(query_data)
    
    # Sort by rank
    trending_queries.sort(key=lambda x: x["rank"])
    
    # Build response
    response = {
        "date": date,
        "trending_queries": trending_queries
    }
    
    # Add pagination token if there are more results
    if "LastEvaluatedKey" in dynamodb_response:
        import base64
        next_token = base64.b64encode(
            json.dumps(dynamodb_response["LastEvaluatedKey"]).encode("utf-8")
        ).decode("utf-8")
        response["next_token"] = next_token
    
    return response
