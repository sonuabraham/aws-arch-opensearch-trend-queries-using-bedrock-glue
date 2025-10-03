"""
Orchestration Construct - Step Functions and EventBridge scheduling
"""
from aws_cdk import (
    Duration,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
    aws_glue as glue,
    aws_lambda as lambda_,
    RemovalPolicy,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig


class OrchestrationConstruct(Construct):
    """Construct for workflow orchestration using Step Functions and EventBridge"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        glue_crawler: glue.CfnCrawler, 
        glue_job: glue.CfnJob,
        clustering_job: glue.CfnJob, 
        classification_function: lambda_.Function,
        step_functions_role: iam.Role = None,
        logs_kms_key = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.glue_crawler = glue_crawler
        self.glue_job = glue_job
        self.clustering_job = clustering_job
        self.classification_function = classification_function
        self.step_functions_role = step_functions_role
        self.logs_kms_key = logs_kms_key
        
        # Create Step Functions state machine
        self._create_state_machine()
        
        # Create EventBridge scheduling
        self._create_eventbridge_schedule()
    
    def _create_state_machine(self) -> None:
        """Define state machine workflow for daily processing"""
        
        # Create CloudWatch log group for Step Functions with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws/stepfunctions/{self.config.resource_prefix}-trending-queries",
            "retention": logs.RetentionDays.TWO_WEEKS,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        log_group = logs.LogGroup(self, "StateMachineLogGroup", **log_group_kwargs)
        
        # Define Step Functions tasks
        
        # Task 1: Start Glue Crawler
        start_crawler_task = tasks.GlueStartCrawlerRun(
            self, "StartGlueCrawler",
            crawler_name=self.glue_crawler.name,
            result_path="$.crawlerResult",
            comment="Start Glue crawler to catalog new search query data"
        )
        
        # Task 2: Run Data Consolidation Job
        consolidation_task = tasks.GlueStartJobRun(
            self, "RunConsolidationJob",
            glue_job_name=self.glue_job.name,
            result_path="$.consolidationResult",
            comment="Run Glue ETL job to consolidate search query data",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB
        )
        
        # Task 3: Run K-means Clustering Job
        clustering_task = tasks.GlueStartJobRun(
            self, "RunClusteringJob",
            glue_job_name=self.clustering_job.name,
            result_path="$.clusteringResult",
            comment="Run K-means clustering analysis on search queries",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB
        )
        
        # Task 4: Invoke Bedrock Classification Lambda
        classification_task = tasks.LambdaInvoke(
            self, "InvokeBedrockClassification",
            lambda_function=self.classification_function,
            payload=sfn.TaskInput.from_object({
                "date.$": "$.date",
                "clusteringJobId.$": "$.clusteringResult.JobRunId"
            }),
            result_path="$.classificationResult",
            comment="Classify trending queries using Amazon Bedrock LLM",
            retry_on_service_exceptions=True
        )
        
        # Task 5: Success state
        success_state = sfn.Succeed(
            self, "WorkflowSuccess",
            comment="Trending queries workflow completed successfully"
        )
        
        # Task 6: Failure state
        failure_state = sfn.Fail(
            self, "WorkflowFailure",
            comment="Trending queries workflow failed",
            cause="Workflow execution encountered an error",
            error="WorkflowExecutionError"
        )
        
        # Define error handling for each task
        
        # Crawler error handling
        crawler_catch = sfn.Catch(
            errors=["States.ALL"],
            result_path="$.error"
        ).next(failure_state)
        
        start_crawler_task.add_catch(crawler_catch)
        
        # Consolidation job error handling
        consolidation_catch = sfn.Catch(
            errors=["States.ALL"],
            result_path="$.error"
        ).next(failure_state)
        
        consolidation_task.add_catch(consolidation_catch)
        consolidation_task.add_retry(
            errors=["Glue.ConcurrentRunsExceededException"],
            interval=Duration.seconds(30),
            max_attempts=3,
            backoff_rate=2.0
        )
        
        # Clustering job error handling
        clustering_catch = sfn.Catch(
            errors=["States.ALL"],
            result_path="$.error"
        ).next(failure_state)
        
        clustering_task.add_catch(clustering_catch)
        clustering_task.add_retry(
            errors=["Glue.ConcurrentRunsExceededException"],
            interval=Duration.seconds(30),
            max_attempts=3,
            backoff_rate=2.0
        )
        
        # Classification Lambda error handling
        classification_catch = sfn.Catch(
            errors=["States.ALL"],
            result_path="$.error"
        ).next(failure_state)
        
        classification_task.add_catch(classification_catch)
        classification_task.add_retry(
            errors=["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
            interval=Duration.seconds(10),
            max_attempts=3,
            backoff_rate=2.0
        )
        
        # Define workflow chain
        workflow_definition = start_crawler_task \
            .next(consolidation_task) \
            .next(clustering_task) \
            .next(classification_task) \
            .next(success_state)
        
        # Use provided role or create fallback role
        if self.step_functions_role:
            state_machine_role = self.step_functions_role
        else:
            # Create IAM role for Step Functions
            state_machine_role = iam.Role(
                self, "StateMachineRole",
                role_name=f"{self.config.resource_prefix}-stepfunctions",
                assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
                description="Role for Step Functions to orchestrate trending queries workflow"
            )
            
            # Grant permissions to start Glue crawler
            state_machine_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "glue:StartCrawler",
                        "glue:GetCrawler"
                    ],
                    resources=[
                        f"arn:aws:glue:{self.region}:{self.account}:crawler/{self.glue_crawler.name}"
                    ]
                )
            )
            
            # Grant permissions to start Glue jobs
            state_machine_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "glue:StartJobRun",
                        "glue:GetJobRun",
                        "glue:GetJobRuns",
                        "glue:BatchStopJobRun"
                    ],
                    resources=[
                        f"arn:aws:glue:{self.region}:{self.account}:job/{self.glue_job.name}",
                        f"arn:aws:glue:{self.region}:{self.account}:job/{self.clustering_job.name}"
                    ]
                )
            )
            
            # Grant permissions to invoke Lambda function
            self.classification_function.grant_invoke(state_machine_role)
            
            # Grant CloudWatch Logs permissions
            state_machine_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogDelivery",
                        "logs:GetLogDelivery",
                        "logs:UpdateLogDelivery",
                        "logs:DeleteLogDelivery",
                        "logs:ListLogDeliveries",
                        "logs:PutResourcePolicy",
                        "logs:DescribeResourcePolicies",
                        "logs:DescribeLogGroups"
                    ],
                    resources=["*"]
                )
            )
        
        # Create the Step Functions state machine
        self.step_function = sfn.StateMachine(
            self, "TrendingQueriesStateMachine",
            state_machine_name=f"{self.config.resource_prefix}-trending-queries",
            definition_body=sfn.DefinitionBody.from_chainable(workflow_definition),
            role=state_machine_role,
            timeout=Duration.hours(2),
            comment="Daily workflow to process and analyze trending search queries",
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            ),
            tracing_enabled=True
        )
    
    def _create_eventbridge_schedule(self) -> None:
        """Define EventBridge rule for daily workflow triggers"""
        
        # Get schedule configuration
        schedule_hour = self.config.get("orchestration", "schedule_hour", 2)
        schedule_minute = self.config.get("orchestration", "schedule_minute", 0)
        timezone = self.config.get("orchestration", "timezone", "UTC")
        
        # Create EventBridge rule for daily scheduling
        # Schedule runs daily at configured time (default: 2:00 AM UTC)
        self.schedule_rule = events.Rule(
            self, "DailyScheduleRule",
            rule_name=f"{self.config.resource_prefix}-daily-schedule",
            description=f"Triggers trending queries workflow daily at {schedule_hour:02d}:{schedule_minute:02d} {timezone}",
            schedule=events.Schedule.cron(
                minute=str(schedule_minute),
                hour=str(schedule_hour),
                month="*",
                week_day="*",
                year="*"
            ),
            enabled=True
        )
        
        # Create IAM role for EventBridge to invoke Step Functions
        eventbridge_role = iam.Role(
            self, "EventBridgeRole",
            role_name=f"{self.config.resource_prefix}-eventbridge",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            description="Role for EventBridge to trigger Step Functions workflow"
        )
        
        # Grant permission to start Step Functions execution
        self.step_function.grant_start_execution(eventbridge_role)
        
        # Add Step Functions as target with input transformation
        self.schedule_rule.add_target(
            targets.SfnStateMachine(
                self.step_function,
                role=eventbridge_role,
                input=events.RuleTargetInput.from_object({
                    "date": events.EventField.from_path("$.time"),
                    "source": "eventbridge-schedule",
                    "scheduledTime": events.EventField.from_path("$.time")
                })
            )
        )
