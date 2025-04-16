#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { ForestClassificationStack } from '../lib/open_earth_foundation_stack';

const app = new cdk.App();
new ForestClassificationStack(app, 'ForestClassificationStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});