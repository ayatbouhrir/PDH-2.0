# DAE-PFAS

**DAE-PFAS** is an enhanced version of the [PFAS Data Hub (PDH)](https://pdh.cnrs.fr/fr/map/), developed at **LIRMM**.  
It provides improved filtering capabilities and better geospatial data visualization for the same PFAS data.

---

## Requirements

Before installing the project, make sure PostgreSQL is available on your machine.

> If PostgreSQL is not installed, you can follow this official guide:  
> [https://www.postgresql.org/download/](https://www.postgresql.org/download/)

Once installed:
- **Create a database** (you can name it e.g. `dae_pfas`)
- Ensure the PostgreSQL server is running and accessible locally.

---

## Installation

1. **Create a local PostgreSQL database** as mentionned in the requirements section.

2. **Clone this repository:**
   ```bash
   git clone https://gite.lirmm.fr/miori/dae-pfas.git
   cd dae-pfas
   ```

3. **Install dependencies:**
   ```bash
   npm install
   ```

4. **Configure environment variables:**
   - Copy the `.env.example` file to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Update the values in `.env` with your PostgreSQL configuration:
     - `DB_HOST`
     - `DB_PORT`
     - `DB_USER`
     - `DB_PASSWORD`
     - `DB_NAME`

5. **Initialize the database:**
   - Run the `init_db.ipynb` notebook located at the root of the project.
   - This will:
     - Download and process the PFAS dataset
     - Create required tables, views, and indexes
     - Populate the database.

---

## Run the App

After initializing the database, you can launch the frontend dev server:

```bash
npm run dev
```

---

## Project Structure

- `init_db.ipynb` – Jupyter Notebook for database initialization and data import.
- `.env.example` – Template file for environment variables.
- `src/` – Source folder for the frontend application.

---

## Notes

- The dataset is large (~3 GB); downloading and processing may take a few hours.
- Ensure PostgreSQL is running and credentials are valid before launching the notebook.
