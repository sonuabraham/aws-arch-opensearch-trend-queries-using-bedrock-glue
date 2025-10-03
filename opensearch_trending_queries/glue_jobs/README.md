# AWS Glue Jobs

This directory contains AWS Glue ETL job scripts for the OpenSearch Trending Queries system.

## K-means Clustering Job

**File:** `kmeans_clustering_job.py`

**Purpose:** Performs vector embedding and K-means clustering on search queries to identify semantic patterns and group similar queries together.

**Features:**
- TF-IDF vector embeddings for search queries
- Stop word removal for better clustering
- Configurable cluster count and max iterations
- Comprehensive error handling and logging
- Cluster statistics generation
- Partitioned output by date

**Parameters:**
- `database_name`: Glue database name
- `processed_data_bucket`: S3 bucket for processed data
- `cluster_count`: Number of clusters (default: 10)
- `max_iterations`: Maximum K-means iterations (default: 20)

**Output:**
- Clustered queries: `s3://{bucket}/clustered-queries/date={date}/`
- Cluster statistics: `s3://{bucket}/cluster-stats/`

**Requirements:** Requirement 2.3 - K-means clustering for grouping similar queries
