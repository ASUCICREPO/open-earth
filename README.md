# Forest Classification Project

## Project Overview
This project provides an AWS Lambda-based solution for land usage classification, focusing on natural forest classification using Google Earth Engine (GEE). The infrastructure is deployed via a provided CloudFormation template, and a frontend interface allows users to upload data and trigger the classification process.

---

## Repository Structure
```
├── backend/                    # AWS CDK Infrastructure as Code
│   ├── bin/                    # CDK app entry point
│   │   └── forest-classification.ts       
│   ├── lambda/                 # Lambda functions for data processing
│   │   ├── lambda-function.py  
│   │   └── lambda-function-code.zip  
│   ├── lib/                    # CDK stack definition
│   │   └── classification_stack.ts     
│   ├── cdk.json                # CDK CLI configuration      
│   ├── package.json            # Node.js dependencies & scripts  
│   ├── requirements.txt        # Python dependencies for Lambdas  
│   └── tsconfig.json           # TypeScript compiler settings   
│
└── frontend/                   # React frontend application
    ├── public/                   
    │   ├── index.html          # HTML shell for mounting the React app  
    │   └── external/           # unbundled assets (images, SVGs, media)  
    ├── src/                            
    │   ├── components/         # reusable UI components           
    │   │   ├── AppHeader.jsx       # top navigation bar with logo & links  
    │   │   ├── ErrorModal.jsx      # modal dialog for displaying errors  
    │   │   └── ProtectedRoute.jsx  # route guard enforcing authentication  
    │   ├── pages/              # view components mapped to routes  
    │   │   ├── Error.jsx           # full‐page error/fallback screen  
    │   │   ├── MapAnalysis.jsx     # interactive map visualization  
    │   │   └── Upload.jsx          # file upload form with validation  
    │   ├── utilities/           # helper functions & service clients  
    │   │   └── apiService.jsx       # centralized API request handler  
    │   ├── index.js             # app entry point that boots React  
    │   └── index.css            # global styles & CSS variables  
    ├── build/                   
    │   ├── index.html            # minified HTML for deployment    
    │   └── open_earth.zip        # zipped bundle of static assets  
    ├── .env                    # environment variable declarations  
    ├── .gitignore              # files & folders to ignore in Git  
    ├── craco.config.js         # CRA config overrides without ejecting  
    ├── package.json            # npm dependencies & project scripts  
    └── package-lock.json       # exact dependency versions lockfile  

```

---

## Prerequisites
Before starting, ensure the following prerequisites are met:

### 1. AWS Account And IAM User
- **Description**: An active AWS account is required to deploy and manage resources.
- **Setup**:
  1. Sign up for an AWS account at [aws.amazon.com](https://aws.amazon.com).
  2. Create an IAM User with Enable Programmatic access and AWS Management Console access.
  3. Install the AWS CLI:
     ```bash
     pip install awscli
     ```
  4. Configure your AWS CLI with credentials:
     ```bash
     aws configure
     ```
     - Provide your AWS Access Key ID, Secret Access Key, region (e.g., `us-east-1`), and output format (e.g., `json`).

### 2. Google Earth Engine (GEE) Service Account
- **Description**: A GEE service account is required to authenticate and access GEE APIs.
- **Setup**:
  1. Sign up for Google Earth Engine at [earthengine.google.com](https://earthengine.google.com).
  2. Create a Google Cloud project and enable the Earth Engine API.
  3. Go to the Google Cloud Console > IAM & Admin > Service Accounts.
  4. Create a service account, assign it Earth Engine access, and download the JSON credentials file (e.g., `ee-credentials.json`).
  5. Store this file securely—it will be uploaded to an S3 bucket later.

### 3. S3 Bucket for Assets
- **Description**: An S3 bucket is required to store Lambda function code, GEE credentials, and Lambda layers.
- **Setup**:
  1. Create an S3 bucket in your AWS account (e.g., `your-assets-bucket`) via the AWS Management Console or CLI:
     ```bash
     aws s3 mb s3://your-assets-bucket --region your-region
     ```
  2. Upload the following files to the bucket:
     - `lambda-function-code.zip`: The zipped Lambda function code (provided).
     - `ee-credentials.json`: The GEE service account credentials file.
     - `layers/earth_engine_layer.zip`: ZIP file containing the Earth Engine Python library (provided).
     - `layers/image_processing.zip`: ZIP file containing image processing libraries (provided).
  3. Example upload command:
     ```bash
     aws s3 cp lambda-function-code.zip s3://your-assets-bucket/
     ```

  ### 4. Local development tools
  
  1. **Python (3.13)**
       - Install Python 3.13 (required for the Lambda runtime) from [Python.org](https://www.python.org/downloads/)
       - Verify installation:
         ```
            python3 --version
         ```
  

  2. **AWS CLI**: To interact with AWS services and set up credentials.

        - [Install AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
     
  3. **npm**  
        - npm is required to install AWS CDK. Install npm by installing Node.js:  
          - [Download Node.js](https://nodejs.org/) (includes npm).  
        - Verify npm installation:  
             ```bash
             npm --version
             ```
  4. **AWS CDK**: For defining cloud infrastructure in code.
        - [Install AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html)  
             ```bash
             npm install -g aws-cdk
             ```

---

## Architecture Overview
![Architecture Diagram](Architechture_Diagram.png).


The system is designed with a modular architecture for scalability and ease of use:

- **Frontend**: 
  - A user-friendly interface where users upload a `data.json` file (containing geospatial boundary data) and specify a date range (`start_date` and `end_date`).
  - Sends requests to the AWS Lambda function to initiate classification and retrieves results.

- **AWS Lambda**:
  - The core processing unit that performs land usage classification using GEE.
  - Triggered by the frontend, it downloads GEE credentials and input data from S3, processes the data, and uploads results back to S3.

- **S3 Buckets**:
  - **Assets Bucket**: Stores static assets like Lambda code, GEE credentials, and Lambda layers (e.g., `your-assets-bucket`).
  - **Input/Output Bucket**: Stores user-uploaded `data.json` files and the resulting classification images and statistics.

- **Google Earth Engine (GEE)**:
  - Provides geospatial data and processing capabilities for land classification, accessed via the Lambda function.

- **CloudFormation**:
  - Deploys the entire infrastructure (Lambda, S3 buckets, IAM roles) using a provided template file.

---

## Setup Instructions
Follow these steps to prepare the project:

### 1. Clone the Repository
```bash
git clone https://github.com/your-repo/forest-classification.git
cd forest-classification
```

### 2. Upload Assets to S3
- **Description**: Upload the necessary files to your assets S3 bucket.
- **Action**:
  ```bash
  aws s3 cp lambda-function-code.zip s3://your-assets-bucket/
  aws s3 cp ee-credentials.json s3://your-assets-bucket/credentials/
  aws s3 cp layers/earth_engine_layer.zip s3://your-assets-bucket/layers/
  aws s3 cp layers/image_processing.zip s3://your-assets-bucket/layers/
  ```

### 3. Start the React App
- **Description**: Verify prerequisites, install dependencies, and launch the development server.
- **Action**:

```bash
 clone the project
 cd Frontend
 node -v         # confirm Node.js is installed
 npm -v          # confirm npm is installed
 npm install     # install project dependencies
 npm start       # start React on http://localhost:3000


```

---


## Deployment
Deploy the infrastructure using the provided CloudFormation template:

### 1. Install Backend Dependencies
- **Description**: 
- **Action**:
  1. cd backend
  2. Install Node.js dependencies:
     ```bash
     npm install
     ```
  4. Ensure package.json includes dependencies like aws-cdk-lib, constructs, and source-map-support.

### 2. Bootstrap the CDK Environment
- **Description**: Bootstrap your AWS account for CDK deployments in backend folder:
- **Action**:
     ```bash
     cdk bootstrap
     ```

### 3. Deploy the CDK Stack
- **Description**: Deploy the ForestClassificationStack with the required parameters:
- **Action**:
     ```bash
         cdk deploy ForestClassificationStack \
      --parameters AssetsBucketName={assets bucket name }\
      --parameters BucketName={bucket name } \
      --parameters GeeCredentialsFile={credentials file name}

     ```

### 4. Verify Deployment
- **Description**: Confirm that resources are created successfully.
- **Action**: Check the AWS Management Console:
  - **S3**: Verify buckets exist.
  - **Lambda**: Confirm the `ForestClassificationLambda` function is deployed.
  - **CloudFormation**: Ensure the stack status is `CREATE_COMPLETE`.
 
### 5. Retrieve the Lambda Function URL
- **Description**: Get the Lambda Function URL from the output of deployed CDK.

---

## Using the Frontend
The frontend provides an easy way to interact with the classification system:
To deploy the Frontend, follow these steps:

1. **Clone & Install Dependencies**
  - Clone the repository:
    git clone <repository-url>
  - Move to the Frontend folder:
    cd <project-root>/Frontend
  - Install all required packages:
    npm install

    
2. **Run Locally**
   - create an .env file in Frontend folder and attach the lambda URL in REACT_APP_API_URL variable. so file would be (REACT_APP_API_URL = {lambda Funtion URL} ).
   - Start the development server:
     npm start
   - If you hit any errors, verify your versions:
     npm -v    # should be ≈ 10.9.2  
     node -v   # should be ≈ v23.9.0

4. **Build for Production**
   - Generate an optimized production build:
      npm run build (This creates a build/ folder).
   - Open the project in your local and zip the contents of the build/ folder (not the folder itself).

5. **Deploy on AWS Amplify**
   - In the Amplify console, choose Create new app → Deploy without Git.
   - Give your app a name and stage, upload the zip, then click Save and deploy.
   - After a short wait, Amplify will present your live application URL

6. **Once Deployed**
   - Upload Data File: Upload a `data.json` file containing geospatial boundary data.
   - Specify Date Range: Enter the `start_date` and `end_date` for the analysis. (Note: For larger JSON files, to get better results without much cloud coverage, choose a larger date range (preferably 1–2 months).
   - Trigger Analysis: Submit the data via the frontend to trigger the Lambda function.
   - View Results: Download the classified image and statistics from the provided dowload button in the frontend.

---

## Additional Notes
- **Security**: Ensure the S3 bucket with `ee-credentials.json` has public access blocked and appropriate IAM policies.
- **Cost Management**: Monitor AWS usage to avoid unexpected charges, especially for large-scale GEE data processing.
- **Updates**: If you modify the Lambda code or layers, re-upload the ZIP files to the assets bucket and update the CloudFormation stack.
