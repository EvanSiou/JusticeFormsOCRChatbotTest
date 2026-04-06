# OCR Demo App

Production-ready document intelligence prototype deployed on AWS. This application demonstrates an end-to-end OCR pipeline for court forms using Amazon Bedrock vision models.

## Architecture

- **Backend**: FastAPI (Python 3.11) served by Uvicorn
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Deployment**: AWS App Runner with Docker (multi-stage build)
- **Storage**: Amazon S3 (document storage)
- **Database**: Amazon DynamoDB (sessions, config, prompts, form types)
- **AI/ML**: Amazon Bedrock (Claude, Nova, Llama, Pixtral vision models)

## Features

- Multi-page document OCR processing via Bedrock vision models
- Document quality detection (orientation, degradation)
- Automated form type identification
- Structured field extraction and classification
- Bias injection for educational testing
- Session management with DynamoDB

## Deployment

Uses AWS CodeBuild (`buildspec.yml`) to build a Docker image and push to ECR. AWS App Runner (`apprunner.yaml`) pulls and runs the container on port 8080.

See `apprunner.yaml` and `buildspec.yml` for deployment configuration.
