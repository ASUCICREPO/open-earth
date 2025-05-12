# Open Earth Foundation Land Usage Classification System

This project provides a system for classifying land usage types within geographical boundaries using satellite imagery and AI-driven geospatial analysis. It integrates Google Earth Engine (GEE) with AWS services to deliver detailed land usage maps and statistics, supporting environmental monitoring and greenhouse gas inventory calculations.

The system consists of a React-based frontend for user interaction and a serverless backend powered by AWS CDK that handles data processing, GEE integration, and result generation. The application leverages GEE for processing satellite imagery and AWS Bedrock for potential future AI enhancements.

## Repository Structure
```
.
├── backend/                    # AWS CDK Infrastructure as Code
│   ├── bin/                    # CDK app entry point
│   │   └── open-earth.ts       # CDK app definition
│   ├── lambda/                 # Lambda functions for data processing
│   │   └── forest_classification/  # Lambda for land usage classification
│   │       └── lambda_function.py  # Main Lambda handler
│   └── lib/                    # CDK stack definition
│       └── forest-stack.ts     # ForestClassificationStack definition
└── frontend/                   # React frontend application
    ├── public/                 # Static assets
    └── src/                    # Source code
        ├── Components/         # React components
        │   └── UploadForm.jsx  # File upload and analysis form
        └── utilities/         # Helper functions and constants
```

## Usage Instructions
### Prerequisites
- **Node.js** 16.x or later
- **AWS CLI** configured with appropriate credentials
- **AWS CDK CLI** installed (`npm install -g aws-cdk`)
- **Python** 3.9 for Lambda functions
- **pip** for installing Python dependencies
- **Google Earth Engine Credentials** (`ee-ridhamsonani3-access_key.json` or your own GEE credentials)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd open-earth
```

2. Install frontend dependencies:
```bash
cd frontend
npm install
```

3. Install backend dependencies:
```bash
cd ../cdk_backend
npm install
```

4. Deploy the CDK stack:
```bash
cdk deploy ForestClassificationStack
```

### Quick Start
1. Start the frontend development server:
```bash
cd frontend
npm start
```

2. Open your browser and navigate to `http://localhost:3000`

3. Upload a GeoJSON file and select a date range to analyze land usage

### More Detailed Examples
1. Analyze land usage for a specific area:
```
- Upload a GeoJSON file with boundary coordinates
- Select a date range (e.g., 2023-06-01 to 2024-07-30)
- View the classified map and area statistics
```

2. Test with different date ranges:
```
- Use a date range with high cloud cover to test error handling
- Analyze a large area to verify processing performance
```

### Troubleshooting
1. S3 Bucket Name Conflict
- Error: "S3 bucket already exists"
  - The stack generates a unique bucket name using your AWS account ID and timestamp
  - If the error persists, specify a custom name with `--parameters s3BucketName=<unique-name>`

2. Lambda Function Errors
- Error: "Lambda function timed out"
  - Check CloudWatch logs for detailed error messages
  - Increase the Lambda timeout in the CDK stack if needed
  - Verify memory allocation (set to 10,240 MB)

3. GEE Authentication Issues
- Error: "Failed to authenticate with Google Earth Engine"
  - Ensure the GEE credentials file is uploaded to S3
  - Verify the `SERVICE_ACCOUNT` matches the credentials file
  - Check Lambda logs for detailed errors

## Data Flow
The system processes GeoJSON files through a pipeline that integrates GEE for geospatial analysis and AWS for storage and compute.

```
[User Input] -> [API Gateway] -> [Lambda Handler] -> [Google Earth Engine]
                                              -> [S3 Storage]
     [UI] <- [HTTP Response] <- [Processed Results]
```

Key component interactions:
- Frontend sends GeoJSON files and date ranges via HTTP POST requests
- API Gateway routes requests to the Lambda function
- Lambda processes the data using GEE (Dynamic World, WDPA datasets)
- Results (classified maps and stats) are stored in S3
- Pre-signed URLs and stats are returned to the UI for display

## Infrastructure

![Infrastructure diagram](./docs/infra.svg)  
*The infrastructure diagram is a placeholder. Create a diagram using tools like draw.io and save it in the `docs/` directory.*

The application is deployed using AWS CDK with the following key resources:

**Lambda Functions:**
- **ForestClassificationLambda**: Processes GeoJSON files, integrates with GEE, and generates classified maps and statistics.

**AWS Services:**
- **S3 Bucket**: Stores GeoJSON files, GEE credentials, Lambda code, and output files (maps, stats).
- **API Gateway**: HTTP API endpoint for frontend-backend communication.
- **IAM**: Roles and permissions for Lambda to access S3 and CloudWatch.
- **CloudWatch**: Logs for monitoring Lambda execution.

**External Services:**
- **Google Earth Engine**: Provides satellite imagery and geospatial datasets (Dynamic World, WDPA).

