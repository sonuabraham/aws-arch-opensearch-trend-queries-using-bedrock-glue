"""
AWS Glue ETL Job Script for Data Consolidation
Consolidates and transforms search query data from raw logs
"""
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime, timedelta

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'database_name',
    'raw_data_bucket',
    'processed_data_bucket'
])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

try:
    # Read search query data from Glue catalog
    search_queries_df = glueContext.create_dynamic_frame.from_catalog(
        database=args['database_name'],
        table_name="search_queries"
    ).toDF()
    
    # Data consolidation and aggregation
    consolidated_df = search_queries_df.groupBy(
        "query_text",
        F.to_date("timestamp").alias("date")
    ).agg(
        F.count("*").alias("query_count"),
        F.countDistinct("user_id").alias("unique_users"),
        F.avg("results_count").alias("avg_results_count"),
        F.avg(F.when(F.col("click_through") == True, 1).otherwise(0)).alias("click_through_rate"),
        F.first("source").alias("source")
    )
    
    # Add partitioning columns
    consolidated_df = consolidated_df.withColumn("year", F.year("date")) \
                                   .withColumn("month", F.month("date")) \
                                   .withColumn("day", F.dayofmonth("date"))
    
    # Write consolidated data to S3 in Parquet format
    consolidated_df.write \
        .mode("overwrite") \
        .partitionBy("year", "month", "day") \
        .parquet(f"s3://{args['processed_data_bucket']}/consolidated-queries/")
    
    print("Data consolidation completed successfully")
    
except Exception as e:
    print(f"Error in data consolidation: {str(e)}")
    raise e
finally:
    job.commit()