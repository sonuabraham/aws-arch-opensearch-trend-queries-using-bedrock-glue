"""
AWS Glue ETL Job Script for K-means Clustering
Performs vector embedding and K-means clustering on search queries
"""
import sys
import logging
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, IntegerType, DoubleType
from pyspark.ml.feature import Tokenizer, HashingTF, IDF, StopWordsRemover
from pyspark.ml.clustering import KMeans
from pyspark.ml import Pipeline
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'database_name',
    'processed_data_bucket',
    'cluster_count',
    'max_iterations'
])

# Parse parameters with defaults
cluster_count = int(args.get('cluster_count', 10))
max_iterations = int(args.get('max_iterations', 20))

logger.info(f"Starting K-means clustering job with {cluster_count} clusters and {max_iterations} max iterations")

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

try:
    logger.info("Reading consolidated data from S3")
    
    # Read consolidated data
    consolidated_df = spark.read.parquet(
        f"s3://{args['processed_data_bucket']}/consolidated-queries/"
    )
    
    # Validate data
    if consolidated_df.count() == 0:
        raise ValueError("No data found in consolidated queries")
    
    logger.info(f"Loaded {consolidated_df.count()} records")
    
    # Filter for recent data (last 7 days) and queries with sufficient volume
    recent_date = datetime.now() - timedelta(days=7)
    recent_df = consolidated_df.filter(
        (F.col("date") >= recent_date) & 
        (F.col("query_count") >= 5)  # Filter low-volume queries
    )
    
    logger.info(f"Filtered to {recent_df.count()} recent high-volume queries")
    
    if recent_df.count() < cluster_count:
        logger.warning(f"Not enough data points ({recent_df.count()}) for {cluster_count} clusters")
        cluster_count = max(2, recent_df.count() // 2)
        logger.info(f"Adjusted cluster count to {cluster_count}")
    
    # Prepare data for clustering - create TF-IDF vectors
    logger.info("Creating vector embeddings using TF-IDF")
    
    # Tokenize query text
    tokenizer = Tokenizer(inputCol="query_text", outputCol="words")
    
    # Remove stop words
    stop_words_remover = StopWordsRemover(
        inputCol="words", 
        outputCol="filtered_words"
    )
    
    # Create term frequency features
    hashingTF = HashingTF(
        inputCol="filtered_words", 
        outputCol="rawFeatures", 
        numFeatures=1000
    )
    
    # Create IDF features (vector embeddings)
    idf = IDF(
        inputCol="rawFeatures", 
        outputCol="features",
        minDocFreq=2
    )
    
    # Create pipeline for feature extraction
    logger.info("Building feature extraction pipeline")
    pipeline = Pipeline(stages=[tokenizer, stop_words_remover, hashingTF, idf])
    
    try:
        model = pipeline.fit(recent_df)
        feature_df = model.transform(recent_df)
        logger.info("Feature extraction completed successfully")
    except Exception as e:
        logger.error(f"Error during feature extraction: {str(e)}")
        raise
    
    # Apply K-means clustering
    logger.info(f"Applying K-means clustering with k={cluster_count}")
    
    kmeans = KMeans(
        k=cluster_count,
        seed=42,
        maxIter=max_iterations,
        featuresCol="features",
        predictionCol="cluster_id",
        initMode="k-means||",
        tol=1e-4
    )
    
    try:
        kmeans_model = kmeans.fit(feature_df)
        clustered_df = kmeans_model.transform(feature_df)
        
        # Log clustering metrics
        wssse = kmeans_model.summary.trainingCost
        logger.info(f"K-means clustering completed. WSSSE: {wssse}")
        
        # Log cluster sizes
        cluster_sizes = clustered_df.groupBy("cluster_id").count().collect()
        for row in cluster_sizes:
            logger.info(f"Cluster {row['cluster_id']}: {row['count']} queries")
            
    except Exception as e:
        logger.error(f"Error during K-means clustering: {str(e)}")
        raise
    
    # Select relevant columns and add metadata
    logger.info("Preparing output data")
    
    result_df = clustered_df.select(
        "query_text",
        "date",
        "query_count",
        "unique_users",
        "avg_results_count",
        "click_through_rate",
        "cluster_id"
    ).withColumn(
        "processing_timestamp",
        F.lit(datetime.now().isoformat())
    ).withColumn(
        "cluster_count",
        F.lit(cluster_count)
    )
    
    # Calculate cluster statistics
    cluster_stats = result_df.groupBy("cluster_id").agg(
        F.count("*").alias("cluster_size"),
        F.sum("query_count").alias("total_queries"),
        F.avg("query_count").alias("avg_query_count"),
        F.collect_list("query_text").alias("sample_queries")
    )
    
    # Write clustering results to S3
    logger.info("Writing clustering results to S3")
    
    output_path = f"s3://{args['processed_data_bucket']}/clustered-queries/"
    
    try:
        result_df.write \
            .mode("overwrite") \
            .partitionBy("date") \
            .parquet(output_path)
        
        logger.info(f"Clustering results written to {output_path}")
    except Exception as e:
        logger.error(f"Error writing clustering results: {str(e)}")
        raise
    
    # Write cluster statistics
    stats_path = f"s3://{args['processed_data_bucket']}/cluster-stats/"
    
    try:
        cluster_stats.write \
            .mode("overwrite") \
            .parquet(stats_path)
        
        logger.info(f"Cluster statistics written to {stats_path}")
    except Exception as e:
        logger.error(f"Error writing cluster statistics: {str(e)}")
        raise
    
    logger.info("K-means clustering job completed successfully")
    
except ValueError as ve:
    logger.error(f"Validation error: {str(ve)}")
    raise
except Exception as e:
    logger.error(f"Unexpected error in clustering job: {str(e)}")
    logger.error(f"Error type: {type(e).__name__}")
    raise
finally:
    job.commit()
