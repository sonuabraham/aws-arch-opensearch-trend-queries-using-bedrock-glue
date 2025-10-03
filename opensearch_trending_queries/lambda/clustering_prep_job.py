"""
AWS Glue ETL Job Script for Clustering Preparation
Prepares data for K-means clustering analysis using TF-IDF vectorization
"""
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.ml.feature import Tokenizer, HashingTF, IDF
from pyspark.ml.clustering import KMeans
from pyspark.ml import Pipeline
from datetime import datetime, timedelta

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'database_name',
    'processed_data_bucket'
])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

try:
    # Read consolidated data
    consolidated_df = spark.read.parquet(
        f"s3://{args['processed_data_bucket']}/consolidated-queries/"
    )
    
    # Filter for recent data (last 7 days)
    recent_date = datetime.now() - timedelta(days=7)
    recent_df = consolidated_df.filter(F.col("date") >= recent_date)
    
    # Prepare data for clustering - create TF-IDF vectors
    tokenizer = Tokenizer(inputCol="query_text", outputCol="words")
    hashingTF = HashingTF(inputCol="words", outputCol="rawFeatures", numFeatures=1000)
    idf = IDF(inputCol="rawFeatures", outputCol="features")
    
    # Create pipeline for feature extraction
    pipeline = Pipeline(stages=[tokenizer, hashingTF, idf])
    model = pipeline.fit(recent_df)
    feature_df = model.transform(recent_df)
    
    # Apply K-means clustering
    kmeans = KMeans(k=10, seed=42, featuresCol="features", predictionCol="cluster_id")
    kmeans_model = kmeans.fit(feature_df)
    clustered_df = kmeans_model.transform(feature_df)
    
    # Select relevant columns and write results
    result_df = clustered_df.select(
        "query_text",
        "date",
        "query_count",
        "unique_users",
        "avg_results_count",
        "click_through_rate",
        "cluster_id"
    )
    
    # Write clustering results to S3
    result_df.write \
        .mode("overwrite") \
        .partitionBy("date") \
        .parquet(f"s3://{args['processed_data_bucket']}/clustered-queries/")
    
    print("Clustering preparation completed successfully")
    
except Exception as e:
    print(f"Error in clustering preparation: {str(e)}")
    raise e
finally:
    job.commit()