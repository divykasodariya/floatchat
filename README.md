# FloatChat Backend

This repository contains the backend for the **FloatChat** project, built with **FastAPI**.  
Follow the steps below to set up and run the server locally.

---

## Prerequisites

Make sure you have the following installed:

- [Python 3.12+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/)
- [Conda](https://docs.conda.io/en/latest/miniconda.html) *(optional, if you're using Conda)*

---

## Setup Instructions

### 1. Deactivate Conda (if active)
If you are currently inside a Conda environment, deactivate it:

```bash
conda deactivate
```

### 2. Create a Virtual Environment
Create a virtual environment named backend inside the project root:

```bash
python -m venv backend
```

### 3. Activate the Virtual Environment
Windows (Command Prompt or PowerShell):

```bash
.\backend\Scripts\activate
```

### 4. Install Required Packages
Install dependencies from requirements.txt:

```bash
pip install -r requirements.txt
```

### 5. Run the FastAPI Server
Start the FastAPI server using Uvicorn:

```bash
uvicorn app.main:app --reload
```
--reload enables automatic reloading when you make changes to the code.
### 6. Install the following folder
https://drive.google.com/drive/folders/17pTRP6MUJ39eUsS937Kwram4saxDWSLr?usp=sharing

Download this folder and move it to intent_classifi folder

### 7. To convert CSVs to Postgres SQL database:
https://drive.google.com/drive/folders/1FB8_XiRZnDpjNrRh7mx23ErV2KJPkjB3?usp=sharing

Download this folder.
#### Do the following steps
  1. Open psqlshell in you computer.
  2. Create database ocean_data.
  3. Create table for each parameter( temp, psal, ph, nitrate, doxy, chla ) with the following code
  ```sql
   CREATE TABLE temp(platform_type TEXT, platform_number INTEGER, time TIMESTAMP, latitude FLOAT, longitude FLOAT, pres FLOAT, temp FLOAT);
  ```
  then execute
  ```sql
  COPY temp FROM 'path_to_temp.csv' WITH(FORMAT csv, HEADER true, ENCODING 'LATIN1');
  ```
  4. Repeat the same steps for all the tables. (Note that the table name for ph is ph and not ph_in_situ_total but the column name in ph table will be ph_in_situ_total)
  5. After completion run the following command to check:
     ```sql
     SELECT * FROM chla LIMIT 1;
     ```
   6. The database is ready.

By default, the server will run at:
http://127.0.0.1:8000
```bash
FLOATCHAT/
│
├── backend/                # Virtual environment
│
├── app/
│   └── main.py              # FastAPI application entry point
│
├── intent_classifi/
│   ├── __init__.py
│   └── classifier.py        # Intent classification logic
│
├── sql_generator/
│   ├── __init__.py
│   └── sql_gen.py           # SQL generation logic
│
└── requirements.txt       # List of dependencies
```

## Summary of Commands
```bash
conda deactivate
python -m venv backend
.\backend\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

# floatchat
