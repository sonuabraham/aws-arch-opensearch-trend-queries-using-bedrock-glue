"""
Monitoring Construct - CloudWatch dashboards, alarms, and X-Ray tracing
"""
from aws_cdk import (
    Duration,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_iam as iam,
    aws_kinesis as kinesis,
    aws_stepfunctions as sfn,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_glue as glue,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig
from typing import Optional


class MonitoringConstruct(Construct):
    """Construct for monitoring and observability using CloudWatch and X-Ray"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        kinesis_stream: Optional[kinesis.Stream] = None,
        step_function: Optional[sfn.StateMachine] = None,
        api_gateway: Optional[apigw.RestApi] = None,
        lambda_functions: Optional[dict] = None,
        trending_queries_table: Optional[dynamodb.Table] = None,
        glue_jobs: Optional[dict] = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.kinesis_stream = kinesis_stream
        self.step_function = step_function
        self.api_gateway = api_gateway
        self.lambda_functions = lambda_functions or {}
        self.trending_queries_table = trending_queries_table
        self.glue_jobs = glue_jobs or {}
        
        # Create SNS topic for alerts
        self._create_sns_topic()
        
        # Create CloudWatch dashboard
        self._create_dashboard()
        
        # Create CloudWatch alarms
        self._create_alarms()
    
    def _create_sns_topic(self) -> None:
        """Create SNS topic for critical alerts"""
        
        # Get alert email from configuration
        alert_email = self.config.get("monitoring", "alert_email", None)
        
        # Create SNS topic for alerts
        self.alert_topic = sns.Topic(
            self, "AlertTopic",
            topic_name=f"{self.config.resource_prefix}-alerts",
            display_name="OpenSearch Trending Queries Alerts"
        )
        
        # Subscribe email if configured
        if alert_email:
            self.alert_topic.add_subscription(
                subscriptions.EmailSubscription(alert_email)
            )
    
    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for system health monitoring"""
        
        # Create dashboard
        self.dashboard = cloudwatch.Dashboard(
            self, "SystemDashboard",
            dashboard_name=f"{self.config.resource_prefix}-dashboard"
        )
        
        # Add widgets to dashboard
        self._add_kinesis_widgets()
        self._add_step_functions_widgets()
        self._add_api_gateway_widgets()
        self._add_lambda_widgets()
        self._add_dynamodb_widgets()
        self._add_glue_widgets()
    
    def _add_kinesis_widgets(self) -> None:
        """Add Kinesis metrics to dashboard"""
        
        if not self.kinesis_stream:
            return
        
        # Kinesis incoming records widget
        kinesis_incoming_widget = cloudwatch.GraphWidget(
            title="Kinesis - Incoming Records",
            left=[
                self.kinesis_stream.metric_incoming_records(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                ),
                self.kinesis_stream.metric_incoming_bytes(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                )
            ],
            width=12
        )
        
        # Kinesis iterator age widget
        kinesis_iterator_widget = cloudwatch.GraphWidget(
            title="Kinesis - Iterator Age",
            left=[
                self.kinesis_stream.metric_get_records_iterator_age_milliseconds(
                    statistic=cloudwatch.Stats.MAXIMUM,
                    period=Duration.minutes(5)
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Milliseconds"
            ),
            width=12
        )
        
        self.dashboard.add_widgets(kinesis_incoming_widget, kinesis_iterator_widget)
    
    def _add_step_functions_widgets(self) -> None:
        """Add Step Functions metrics to dashboard"""
        
        if not self.step_function:
            return
        
        # Step Functions execution metrics
        sf_executions_widget = cloudwatch.GraphWidget(
            title="Step Functions - Executions",
            left=[
                self.step_function.metric_started(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.hours(1)
                ),
                self.step_function.metric_succeeded(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.hours(1)
                ),
                self.step_function.metric_failed(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.hours(1)
                ),
                self.step_function.metric_timed_out(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.hours(1)
                )
            ],
            width=12
        )
        
        # Step Functions duration widget
        sf_duration_widget = cloudwatch.GraphWidget(
            title="Step Functions - Execution Duration",
            left=[
                self.step_function.metric_time(
                    statistic=cloudwatch.Stats.AVERAGE,
                    period=Duration.hours(1)
                ),
                self.step_function.metric_time(
                    statistic=cloudwatch.Stats.MAXIMUM,
                    period=Duration.hours(1)
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Milliseconds"
            ),
            width=12
        )
        
        self.dashboard.add_widgets(sf_executions_widget, sf_duration_widget)
    
    def _add_api_gateway_widgets(self) -> None:
        """Add API Gateway metrics to dashboard"""
        
        if not self.api_gateway:
            return
        
        # API Gateway request metrics
        api_requests_widget = cloudwatch.GraphWidget(
            title="API Gateway - Requests",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGateway",
                    metric_name="Count",
                    dimensions_map={
                        "ApiName": self.api_gateway.rest_api_name
                    },
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                )
            ],
            width=8
        )
        
        # API Gateway error metrics
        api_errors_widget = cloudwatch.GraphWidget(
            title="API Gateway - Errors",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGateway",
                    metric_name="4XXError",
                    dimensions_map={
                        "ApiName": self.api_gateway.rest_api_name
                    },
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5),
                    color=cloudwatch.Color.ORANGE
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApiGateway",
                    metric_name="5XXError",
                    dimensions_map={
                        "ApiName": self.api_gateway.rest_api_name
                    },
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5),
                    color=cloudwatch.Color.RED
                )
            ],
            width=8
        )
        
        # API Gateway latency metrics
        api_latency_widget = cloudwatch.GraphWidget(
            title="API Gateway - Latency",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGateway",
                    metric_name="Latency",
                    dimensions_map={
                        "ApiName": self.api_gateway.rest_api_name
                    },
                    statistic=cloudwatch.Stats.AVERAGE,
                    period=Duration.minutes(5)
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApiGateway",
                    metric_name="Latency",
                    dimensions_map={
                        "ApiName": self.api_gateway.rest_api_name
                    },
                    statistic=cloudwatch.Stats.p99,
                    period=Duration.minutes(5)
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Milliseconds"
            ),
            width=8
        )
        
        self.dashboard.add_widgets(api_requests_widget, api_errors_widget, api_latency_widget)
    
    def _add_lambda_widgets(self) -> None:
        """Add Lambda function metrics to dashboard"""
        
        if not self.lambda_functions:
            return
        
        # Collect all Lambda function metrics
        invocation_metrics = []
        error_metrics = []
        duration_metrics = []
        
        for name, function in self.lambda_functions.items():
            invocation_metrics.append(
                function.metric_invocations(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5),
                    label=name
                )
            )
            error_metrics.append(
                function.metric_errors(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5),
                    label=name
                )
            )
            duration_metrics.append(
                function.metric_duration(
                    statistic=cloudwatch.Stats.AVERAGE,
                    period=Duration.minutes(5),
                    label=name
                )
            )
        
        # Lambda invocations widget
        if invocation_metrics:
            lambda_invocations_widget = cloudwatch.GraphWidget(
                title="Lambda - Invocations",
                left=invocation_metrics,
                width=12
            )
            self.dashboard.add_widgets(lambda_invocations_widget)
        
        # Lambda errors widget
        if error_metrics:
            lambda_errors_widget = cloudwatch.GraphWidget(
                title="Lambda - Errors",
                left=error_metrics,
                width=12
            )
            self.dashboard.add_widgets(lambda_errors_widget)
        
        # Lambda duration widget
        if duration_metrics:
            lambda_duration_widget = cloudwatch.GraphWidget(
                title="Lambda - Duration",
                left=duration_metrics,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Milliseconds"
                ),
                width=12
            )
            self.dashboard.add_widgets(lambda_duration_widget)
    
    def _add_dynamodb_widgets(self) -> None:
        """Add DynamoDB metrics to dashboard"""
        
        if not self.trending_queries_table:
            return
        
        # DynamoDB read/write capacity widget
        dynamodb_capacity_widget = cloudwatch.GraphWidget(
            title="DynamoDB - Consumed Capacity",
            left=[
                self.trending_queries_table.metric_consumed_read_capacity_units(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                ),
                self.trending_queries_table.metric_consumed_write_capacity_units(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                )
            ],
            width=12
        )
        
        # DynamoDB throttling widget
        dynamodb_throttle_widget = cloudwatch.GraphWidget(
            title="DynamoDB - Throttled Requests",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="UserErrors",
                    dimensions_map={
                        "TableName": self.trending_queries_table.table_name
                    },
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                ),
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="SystemErrors",
                    dimensions_map={
                        "TableName": self.trending_queries_table.table_name
                    },
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                )
            ],
            width=12
        )
        
        self.dashboard.add_widgets(dynamodb_capacity_widget, dynamodb_throttle_widget)
    
    def _add_glue_widgets(self) -> None:
        """Add Glue job metrics to dashboard"""
        
        if not self.glue_jobs:
            return
        
        # Create widgets for each Glue job
        for job_name, job in self.glue_jobs.items():
            # Glue job success/failure widget
            glue_status_widget = cloudwatch.GraphWidget(
                title=f"Glue Job - {job_name} Status",
                left=[
                    cloudwatch.Metric(
                        namespace="Glue",
                        metric_name="glue.driver.aggregate.numCompletedTasks",
                        dimensions_map={
                            "JobName": job.name,
                            "Type": "count"
                        },
                        statistic=cloudwatch.Stats.SUM,
                        period=Duration.hours(1)
                    )
                ],
                width=12
            )
            self.dashboard.add_widgets(glue_status_widget)
    
    def _create_alarms(self) -> None:
        """Configure alarms for error rates and performance thresholds"""
        
        self._create_step_functions_alarms()
        self._create_api_gateway_alarms()
        self._create_lambda_alarms()
        self._create_dynamodb_alarms()
    
    def _create_step_functions_alarms(self) -> None:
        """Create alarms for Step Functions workflow failures"""
        
        if not self.step_function:
            return
        
        # Alarm for Step Functions execution failures
        sf_failure_alarm = cloudwatch.Alarm(
            self, "StepFunctionsFailureAlarm",
            alarm_name=f"{self.config.resource_prefix}-stepfunctions-failures",
            alarm_description="Alert when Step Functions workflow fails",
            metric=self.step_function.metric_failed(
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Add SNS action
        sf_failure_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Alarm for Step Functions execution timeouts
        sf_timeout_alarm = cloudwatch.Alarm(
            self, "StepFunctionsTimeoutAlarm",
            alarm_name=f"{self.config.resource_prefix}-stepfunctions-timeouts",
            alarm_description="Alert when Step Functions workflow times out",
            metric=self.step_function.metric_timed_out(
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        sf_timeout_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
    
    def _create_api_gateway_alarms(self) -> None:
        """Create alarms for API Gateway errors and latency"""
        
        if not self.api_gateway:
            return
        
        # Alarm for high 5XX error rate
        api_5xx_alarm = cloudwatch.Alarm(
            self, "ApiGateway5XXAlarm",
            alarm_name=f"{self.config.resource_prefix}-api-5xx-errors",
            alarm_description="Alert when API Gateway 5XX error rate is high",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="5XXError",
                dimensions_map={
                    "ApiName": self.api_gateway.rest_api_name
                },
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        api_5xx_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Alarm for high 4XX error rate
        api_4xx_alarm = cloudwatch.Alarm(
            self, "ApiGateway4XXAlarm",
            alarm_name=f"{self.config.resource_prefix}-api-4xx-errors",
            alarm_description="Alert when API Gateway 4XX error rate is high",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="4XXError",
                dimensions_map={
                    "ApiName": self.api_gateway.rest_api_name
                },
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=50,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        api_4xx_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Alarm for high latency
        api_latency_alarm = cloudwatch.Alarm(
            self, "ApiGatewayLatencyAlarm",
            alarm_name=f"{self.config.resource_prefix}-api-high-latency",
            alarm_description="Alert when API Gateway latency is high",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="Latency",
                dimensions_map={
                    "ApiName": self.api_gateway.rest_api_name
                },
                statistic=cloudwatch.Stats.p99,
                period=Duration.minutes(5)
            ),
            threshold=3000,  # 3 seconds
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        api_latency_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
    
    def _create_lambda_alarms(self) -> None:
        """Create alarms for Lambda function errors and throttling"""
        
        if not self.lambda_functions:
            return
        
        for name, function in self.lambda_functions.items():
            # Alarm for Lambda errors
            lambda_error_alarm = cloudwatch.Alarm(
                self, f"LambdaErrorAlarm{name}",
                alarm_name=f"{self.config.resource_prefix}-lambda-{name}-errors",
                alarm_description=f"Alert when Lambda function {name} has errors",
                metric=function.metric_errors(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                ),
                threshold=5,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )
            
            lambda_error_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
            
            # Alarm for Lambda throttling
            lambda_throttle_alarm = cloudwatch.Alarm(
                self, f"LambdaThrottleAlarm{name}",
                alarm_name=f"{self.config.resource_prefix}-lambda-{name}-throttles",
                alarm_description=f"Alert when Lambda function {name} is throttled",
                metric=function.metric_throttles(
                    statistic=cloudwatch.Stats.SUM,
                    period=Duration.minutes(5)
                ),
                threshold=10,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )
            
            lambda_throttle_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
    
    def _create_dynamodb_alarms(self) -> None:
        """Create alarms for DynamoDB throttling and errors"""
        
        if not self.trending_queries_table:
            return
        
        # Alarm for DynamoDB user errors (throttling)
        dynamodb_user_errors_alarm = cloudwatch.Alarm(
            self, "DynamoDBUserErrorsAlarm",
            alarm_name=f"{self.config.resource_prefix}-dynamodb-user-errors",
            alarm_description="Alert when DynamoDB has user errors (throttling)",
            metric=cloudwatch.Metric(
                namespace="AWS/DynamoDB",
                metric_name="UserErrors",
                dimensions_map={
                    "TableName": self.trending_queries_table.table_name
                },
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        dynamodb_user_errors_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
        
        # Alarm for DynamoDB system errors
        dynamodb_system_errors_alarm = cloudwatch.Alarm(
            self, "DynamoDBSystemErrorsAlarm",
            alarm_name=f"{self.config.resource_prefix}-dynamodb-system-errors",
            alarm_description="Alert when DynamoDB has system errors",
            metric=cloudwatch.Metric(
                namespace="AWS/DynamoDB",
                metric_name="SystemErrors",
                dimensions_map={
                    "TableName": self.trending_queries_table.table_name
                },
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        dynamodb_system_errors_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
