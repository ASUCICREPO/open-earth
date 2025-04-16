import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from 'path';

export class ForestClassificationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Retrieve context variables
    const bucketName = this.node.tryGetContext('bucket_name') || 'open-earth-foundation';
    const geeServiceAccount = this.node.tryGetContext('gee_service_account') || 'default-service-account@project.iam.gserviceaccount.com';
    const geeCredentialsFile = this.node.tryGetContext('gee_credentials_file') || 'gee-credentials.json';

    // Create an S3 bucket for storing input/output files
    const bucket = new s3.Bucket(this, 'ForestClassificationBucket', {
      bucketName: bucketName,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Create the Lambda function layers
    const earthEngineLayer = new lambda.LayerVersion(this, 'EarthEngineLayer', {
        code: lambda.Code.fromAsset(path.join(__dirname, 'layers', 'earth_engine')),
        compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
        description: 'Earth Engine API and dependencies',
      });
  
    const imageProcessingLayer = new lambda.LayerVersion(this, 'ImageProcessingLayer', {
    code: lambda.Code.fromAsset(path.join(__dirname, 'layers', 'image_processing')),
    compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
    description: 'PIL, Shapely, and other image processing libraries',
    });

    // Create the Lambda function
    const forestClassificationLambda = new lambda.Function(this, 'ForestClassificationLambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'Natural_forest_classification.lambda_handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: 10240, // Maximum memory: 10,240 MB
      timeout: cdk.Duration.seconds(900), // Maximum runtime: 15 minutes (900 seconds)
      environment: {
        S3_BUCKET: bucket.bucketName,
        GEE_SERVICE_ACCOUNT: geeServiceAccount,
        GEE_CREDENTIALS_FILE: geeCredentialsFile,
      },
      layers: [earthEngineLayer, imageProcessingLayer],
    });

    // Grant the Lambda function permissions to read/write to the S3 bucket
    bucket.grantReadWrite(forestClassificationLambda);
    forestClassificationLambda.addToRolePolicy(
        new iam.PolicyStatement({
          actions: [
            's3:GetObject',
            's3:PutObject',
            's3:ListBucket',
            's3:DeleteObject',
          ],
          resources: [
            bucket.bucketArn,
            `${bucket.bucketArn}/*`, // Allow access to all objects in the bucket
          ],
        })
      );

    // Grant the Lambda function permissions to write logs
    forestClassificationLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [
            `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/${forestClassificationLambda.functionName}:*`,
        ],
      })
    );
    

    // Output the Lambda function ARN, S3 bucket name, and instructions
    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: forestClassificationLambda.functionArn,
      description: 'The ARN of the Forest Classification Lambda function',
    });

    new cdk.CfnOutput(this, 'S3BucketName', {
      value: bucket.bucketName,
      description: 'The name of the S3 bucket',
    });

    new cdk.CfnOutput(this, 'UploadInstruction', {
      value: `Upload your Google Earth Engine credentials file to s3://${bucket.bucketName}/${geeCredentialsFile}`,
      description: 'Instructions for uploading GEE credentials',
    });
  }
}