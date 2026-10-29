import 'dotenv/config';
import { Pool } from 'pg';

const pool = new Pool({
	host: process.env.DB_HOST,
	user: process.env.DB_USER,
	password: process.env.DB_PASSWORD,
	database: process.env.DB_NAME,
	port: parseInt(process.env.DB_PORT || '5432', 10)
});

export default pool;
