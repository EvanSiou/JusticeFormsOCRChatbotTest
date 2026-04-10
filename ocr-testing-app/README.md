# Court Form OCR Testing App

Multi-user web application for testing OCR/layout detection pipelines on court forms. Deployed on AWS.

## Features

- **Manage Forms**: Upload and manage base form templates
- **Generate Synthetic Data**: Create filled forms with synthetic data for testing
- **Run Tests**: Process documents with configurable layout detection and OCR libraries
- **View Results**: Side-by-side comparison of expected vs extracted data
- **Metrics**: Aggregate accuracy metrics and per-field breakdown

## Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React + Vite + TailwindCSS
- **Database**: Amazon DynamoDB
- **Storage**: Amazon S3
- **AI/ML**: Amazon Bedrock (Claude, Nova, Llama, Pixtral)
- **Auth**: JWT-based authentication
- **Deployment**: AWS App Runner via CodeBuild + ECR

## Setup

### 1. Provision DynamoDB Tables

```bash
python setup_dynamodb.py --prefix ocr-testing --region us-west-2
```

### 2. Create S3 Bucket

```bash
aws s3 mb s3://ocr-testing-app-forms --region us-west-2
```

### 3. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your AWS credentials
```

### 4. Frontend Setup

```bash
cd frontend
npm install
```

### 5. Run Development Servers

```bash
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

## Environment Variables

See `backend/.env.example` for all available settings.

## Deployment

See `buildspec.yml` for the AWS CodeBuild CI/CD pipeline.

## API Documentation

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
