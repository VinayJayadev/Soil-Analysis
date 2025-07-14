"""
Database manager for SQLite operations in the geospatial soil analysis pipeline.
Handles schema creation, data operations, and logging integration.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import geopandas as gpd
from logger import DatabaseLogger


class DatabaseManager:
    """
    Manages SQLite database operations for the soil analysis pipeline.
    """
    
    def __init__(self, db_path: str, logger: DatabaseLogger):
        """
        Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file
            logger: Database logger instance
        """
        self.db_path = Path(db_path)
        self.logger = logger
        self.connection = None
        
        # Create database directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self.init_database()
    
    def init_database(self):
        """Initialize the database with schema and indexes."""
        self.logger.pipeline_logger.log_stage_start("Database Initialization", "Creating database schema")
        
        try:
            # Create connection
            self.connection = sqlite3.connect(str(self.db_path))
            self.connection.execute("PRAGMA foreign_keys = ON")
            
            # Create tables
            self._create_tables()
            
            # Create indexes
            self._create_indexes()
            
            self.logger.pipeline_logger.log_stage_complete("Database Initialization", {"database": str(self.db_path)})
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Database initialization failed", "Database Initialization")
            raise
    
    def _create_tables(self):
        """Create all database tables."""
        start_time = time.time()
        
        # Soil samples table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS soil_samples (
                id INTEGER PRIMARY KEY,
                raw_data_id TEXT UNIQUE NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                soc_percent REAL NOT NULL,
                soc_method TEXT,
                top_depth_cm INTEGER NOT NULL,
                bottom_depth_cm INTEGER NOT NULL,
                sampling_date TEXT,
                lab_analysis_date TEXT,
                country_id INTEGER,
                cluster_id INTEGER,
                clay_fraction REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (country_id) REFERENCES countries(id),
                FOREIGN KEY (cluster_id) REFERENCES clusters(id)
            )
        """)
        
        # Countries table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS countries (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                iso_code TEXT,
                boundary_geojson TEXT NOT NULL,
                sample_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Clusters table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY,
                country_id INTEGER NOT NULL,
                cluster_number INTEGER NOT NULL,
                center_latitude REAL NOT NULL,
                center_longitude REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (country_id) REFERENCES countries(id),
                UNIQUE(country_id, cluster_number)
            )
        """)
        
        # Analysis results table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY,
                country_id INTEGER NOT NULL,
                sampling_method TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                soc_mean REAL NOT NULL,
                soc_variance REAL NOT NULL,
                clay_fraction_mean REAL NOT NULL,
                analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (country_id) REFERENCES countries(id)
            )
        """)
        
        # Pipeline logs table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_logs (
                id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                log_level TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_ms INTEGER,
                record_count INTEGER,
                error_details TEXT
            )
        """)
        
        self.connection.commit()
        duration = time.time() - start_time
        
        self.logger.log_transaction("create_tables", "all", 5, duration)
        self.logger.pipeline_logger.logger.info("Database tables created successfully")
    
    def _create_indexes(self):
        """Create database indexes for performance optimization."""
        start_time = time.time()
        
        # Soil samples indexes
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_soil_samples_location ON soil_samples(latitude, longitude)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_soil_samples_country ON soil_samples(country_id)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_soil_samples_soc ON soil_samples(soc_percent)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_soil_samples_cluster ON soil_samples(cluster_id)")
        
        # Countries indexes
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_countries_name ON countries(name)")
        
        # Clusters indexes
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_clusters_country ON clusters(country_id)")
        
        # Analysis results indexes
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_analysis_results_country ON analysis_results(country_id)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_analysis_results_date ON analysis_results(analysis_date)")
        
        # Pipeline logs indexes
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_logs_run_id ON pipeline_logs(run_id)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_logs_timestamp ON pipeline_logs(timestamp)")
        
        self.connection.commit()
        duration = time.time() - start_time
        
        self.logger.log_transaction("create_indexes", "all", 10, duration)
        self.logger.pipeline_logger.logger.info("Database indexes created successfully")
    
    def insert_soil_samples(self, samples_df: pd.DataFrame) -> int:
        """
        Insert soil samples into the database.
        
        Args:
            samples_df: DataFrame with soil sample data
            
        Returns:
            Number of records inserted
        """
        start_time = time.time()
        
        try:
            # Prepare data for insertion
            data_to_insert = []
            for _, row in samples_df.iterrows():
                data_to_insert.append((
                    row['raw_data_id'],
                    row['latitude'],
                    row['longitude'],
                    row['soc_percent'],
                    row.get('soc_method', ''),
                    row['top_depth_cm'],
                    row['bottom_depth_cm'],
                    row.get('sampling_date', ''),
                    row.get('lab_analysis_date', ''),
                    row.get('clay_fraction', 0.0)
                ))
            
            # Bulk insert
            cursor = self.connection.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO soil_samples 
                (raw_data_id, latitude, longitude, soc_percent, soc_method, 
                 top_depth_cm, bottom_depth_cm, sampling_date, lab_analysis_date, clay_fraction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data_to_insert)
            
            self.connection.commit()
            duration = time.time() - start_time
            record_count = len(data_to_insert)
            
            self.logger.log_transaction("insert", "soil_samples", record_count, duration)
            self.logger.pipeline_logger.log_data_loaded("soil_samples", record_count, duration)
            
            return record_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Soil samples insertion failed", "Data Loading")
            raise
    
    def insert_countries(self, countries_data: List[Dict]) -> int:
        """
        Insert country boundaries into the database.
        
        Args:
            countries_data: List of country data dictionaries with geometry information
            
        Returns:
            Number of countries inserted
        """
        start_time = time.time()
        
        try:
            # Prepare data for insertion
            data_to_insert = []
            for country in countries_data:
                # Convert geometry to GeoJSON string
                geojson_str = json.dumps(country['geometry_wkt'])
                data_to_insert.append((
                    country['country_name'],
                    country['country_code'],
                    geojson_str
                ))
            
            # Bulk insert
            cursor = self.connection.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO countries (name, iso_code, boundary_geojson)
                VALUES (?, ?, ?)
            """, data_to_insert)
            
            self.connection.commit()
            duration = time.time() - start_time
            record_count = len(data_to_insert)
            
            self.logger.log_transaction("insert", "countries", record_count, duration)
            self.logger.pipeline_logger.log_data_loaded("countries", record_count, duration)
            
            return record_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Countries insertion failed", "Data Loading")
            raise
    
    def update_country_assignments(self, soil_country_mapping: Dict[int, int]) -> int:
        """
        Update country assignments for soil samples.
        
        Args:
            soil_country_mapping: Dictionary mapping soil sample IDs to country IDs
            
        Returns:
            Number of records updated
        """
        start_time = time.time()
        
        try:
            cursor = self.connection.cursor()
            
            # Update country assignments
            updated_count = 0
            for soil_id, country_id in soil_country_mapping.items():
                cursor.execute("""
                    UPDATE soil_samples 
                    SET country_id = ? 
                    WHERE id = ?
                """, (country_id, soil_id))
                if cursor.rowcount > 0:
                    updated_count += 1
            
            self.logger.pipeline_logger.logger.info(f"Actually updated {updated_count} soil samples in database")
            
            # Update country sample counts
            cursor.execute("""
                UPDATE countries 
                SET sample_count = (
                    SELECT COUNT(*) 
                    FROM soil_samples 
                    WHERE soil_samples.country_id = countries.id
                )
            """)
            
            self.connection.commit()
            duration = time.time() - start_time
            record_count = len(soil_country_mapping)
            
            self.logger.log_transaction("update", "soil_samples", record_count, duration)
            self.logger.pipeline_logger.logger.info(f"Updated country assignments for {record_count} soil samples")
            
            return record_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Country assignment update failed", "Spatial Association")
            raise
    
    def get_random_samples(self, country_id: int, sample_size: int) -> List[Dict[str, Any]]:
        """
        Get random samples from a specific country.
        
        Args:
            country_id: Country ID
            sample_size: Number of samples to retrieve
            
        Returns:
            List of sample dictionaries
        """
        start_time = time.time()
        
        try:
            query = """
                SELECT * FROM soil_samples 
                WHERE country_id = ? 
                ORDER BY RANDOM() 
                LIMIT ?
            """
            
            cursor = self.connection.cursor()
            cursor.execute(query, (country_id, sample_size))
            
            # Convert to list of dictionaries
            columns = [description[0] for description in cursor.description]
            samples = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            duration = time.time() - start_time
            self.logger.log_query(query, (country_id, sample_size), duration)
            
            return samples
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, f"Random sampling failed for country {country_id}", "Sampling")
            raise
    
    def calculate_country_statistics(self, country_id: int, sample_ids: List[int]) -> Dict[str, float]:
        """
        Calculate statistics for a country based on sample IDs.
        
        Args:
            country_id: Country ID
            sample_ids: List of sample IDs to include in calculation
            
        Returns:
            Dictionary with statistics
        """
        start_time = time.time()
        
        try:
            if not sample_ids:
                return {"soc_mean": 0.0, "soc_variance": 0.0, "clay_fraction_mean": 0.0}
            
            # Create placeholders for IN clause
            placeholders = ','.join(['?' for _ in sample_ids])
            
            query = f"""
                SELECT 
                    AVG(soc_percent) as soc_mean,
                    (AVG(soc_percent * soc_percent) - AVG(soc_percent) * AVG(soc_percent)) as soc_variance,
                    AVG(clay_fraction) as clay_fraction_mean
                FROM soil_samples 
                WHERE id IN ({placeholders})
            """
            
            cursor = self.connection.cursor()
            cursor.execute(query, sample_ids)
            result = cursor.fetchone()
            
            duration = time.time() - start_time
            self.logger.log_query(query, sample_ids, duration)
            
            return {
                "soc_mean": result[0] or 0.0,
                "soc_variance": result[1] or 0.0,
                "clay_fraction_mean": result[2] or 0.0
            }
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, f"Statistics calculation failed for country {country_id}", "Statistics")
            raise
    
    def store_clusters(self, clustering_results: Dict[int, List[Dict]]) -> int:
        """
        Store clustering results in the database.
        
        Args:
            clustering_results: Dictionary mapping country IDs to list of cluster data
            
        Returns:
            Number of clusters stored
        """
        start_time = time.time()
        
        try:
            # Prepare data for insertion
            data_to_insert = []
            for country_id, clusters in clustering_results.items():
                for cluster in clusters:
                    data_to_insert.append((
                        country_id,
                        cluster['cluster_number'],
                        cluster['center_latitude'],
                        cluster['center_longitude'],
                        cluster['sample_count']
                    ))
            
            # Bulk insert clusters
            cursor = self.connection.cursor()
            cursor.executemany("""
                INSERT INTO clusters 
                (country_id, cluster_number, center_latitude, center_longitude, sample_count)
                VALUES (?, ?, ?, ?, ?)
            """, data_to_insert)
            
            self.connection.commit()
            duration = time.time() - start_time
            record_count = len(data_to_insert)
            
            self.logger.log_transaction("insert", "clusters", record_count, duration)
            self.logger.pipeline_logger.logger.info(f"Stored {record_count} clusters")
            
            return record_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Clusters storage failed", "Clustering")
            raise
    
    def update_cluster_assignments(self, clustering_results: Dict[int, List[Dict]]) -> int:
        """
        Update cluster assignments for soil samples.
        
        Args:
            clustering_results: Dictionary mapping country IDs to list of cluster data
            
        Returns:
            Number of records updated
        """
        start_time = time.time()
        
        try:
            cursor = self.connection.cursor()
            
            # Get cluster IDs for mapping
            cluster_id_mapping = {}
            for country_id, clusters in clustering_results.items():
                for cluster in clusters:
                    # Get the cluster ID from the database
                    cursor.execute("""
                        SELECT id FROM clusters 
                        WHERE country_id = ? AND cluster_number = ?
                    """, (country_id, cluster['cluster_number']))
                    
                    cluster_row = cursor.fetchone()
                    if cluster_row:
                        cluster_id = cluster_row[0]
                        for sample_id in cluster['sample_ids']:
                            cluster_id_mapping[sample_id] = cluster_id
            
            # Update soil samples with cluster assignments
            updated_count = 0
            for sample_id, cluster_id in cluster_id_mapping.items():
                cursor.execute("""
                    UPDATE soil_samples 
                    SET cluster_id = ? 
                    WHERE id = ?
                """, (cluster_id, sample_id))
                if cursor.rowcount > 0:
                    updated_count += 1
            
            self.connection.commit()
            duration = time.time() - start_time
            
            self.logger.log_transaction("update", "soil_samples_cluster", updated_count, duration)
            self.logger.pipeline_logger.logger.info(f"Updated cluster assignments for {updated_count} soil samples")
            
            return updated_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Cluster assignment update failed", "Clustering")
            raise
    
    def store_analysis_results(self, results: List[Dict[str, Any]]) -> int:
        """
        Store analysis results in the database.
        
        Args:
            results: List of analysis result dictionaries
            
        Returns:
            Number of results stored
        """
        start_time = time.time()
        
        try:
            data_to_insert = []
            for result in results:
                data_to_insert.append((
                    result['country_id'],
                    result['sampling_method'],
                    result['sample_size'],
                    result['soc_mean'],
                    result['soc_variance'],
                    result['clay_fraction_mean']
                ))
            
            cursor = self.connection.cursor()
            cursor.executemany("""
                INSERT INTO analysis_results 
                (country_id, sampling_method, sample_size, soc_mean, soc_variance, clay_fraction_mean)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data_to_insert)
            
            self.connection.commit()
            duration = time.time() - start_time
            record_count = len(data_to_insert)
            
            self.logger.log_transaction("insert", "analysis_results", record_count, duration)
            self.logger.pipeline_logger.logger.info(f"Stored {record_count} analysis results")
            
            return record_count
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Analysis results storage failed", "Analysis")
            raise
    
    def get_soil_samples(self) -> pd.DataFrame:
        """
        Get all soil samples from the database.
        
        Returns:
            DataFrame with soil sample data
        """
        start_time = time.time()
        
        try:
            query = """
                SELECT 
                    id, raw_data_id, latitude, longitude, soc_percent, 
                    soc_method, top_depth_cm, bottom_depth_cm, 
                    sampling_date, lab_analysis_date, country_id, 
                    cluster_id, clay_fraction, created_at
                FROM soil_samples
                ORDER BY id
            """
            
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            columns = [description[0] for description in cursor.description]
            data = cursor.fetchall()
            
            df = pd.DataFrame(data, columns=columns)
            
            duration = time.time() - start_time
            self.logger.log_query(query, None, duration)
            
            return df
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Failed to get soil samples", "Query")
            raise
    
    def get_countries(self) -> pd.DataFrame:
        """
        Get all countries from the database.
        
        Returns:
            DataFrame with country data
        """
        start_time = time.time()
        
        try:
            query = """
                SELECT 
                    id, name, iso_code, boundary_geojson, 
                    sample_count, created_at
                FROM countries
                ORDER BY id
            """
            
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            columns = [description[0] for description in cursor.description]
            data = cursor.fetchall()
            
            df = pd.DataFrame(data, columns=columns)
            
            duration = time.time() - start_time
            self.logger.log_query(query, None, duration)
            
            return df
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Failed to get countries", "Query")
            raise
    
    def get_countries_with_samples(self) -> List[Dict[str, Any]]:
        """
        Get all countries that have soil samples.
        
        Returns:
            List of country dictionaries with sample counts
        """
        start_time = time.time()
        
        try:
            query = """
                SELECT 
                    c.id, c.name, c.iso_code, c.sample_count
                FROM countries c
                WHERE c.sample_count > 0
                ORDER BY c.sample_count DESC
            """
            
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            columns = [description[0] for description in cursor.description]
            countries = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            duration = time.time() - start_time
            self.logger.log_query(query, None, duration)
            
            return countries
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Failed to get countries with samples", "Query")
            raise
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            cursor = self.connection.cursor()
            
            # Get table counts
            cursor.execute("SELECT COUNT(*) FROM soil_samples")
            soil_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM countries")
            country_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM analysis_results")
            analysis_count = cursor.fetchone()[0]
            
            # Get countries with samples
            cursor.execute("SELECT COUNT(*) FROM countries WHERE sample_count > 0")
            countries_with_samples = cursor.fetchone()[0]
            
            return {
                "soil_samples": soil_count,
                "countries": country_count,
                "analysis_results": analysis_count,
                "countries_with_samples": countries_with_samples
            }
            
        except Exception as e:
            self.logger.pipeline_logger.log_error(e, "Failed to get database statistics", "Query")
            raise
    
    def database_exists_and_has_data(self) -> bool:
        """Check if database exists and has data."""
        try:
            if not self.db_path.exists():
                return False
            
            # Check if soil_samples table exists and has data
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='soil_samples'")
            if not cursor.fetchone():
                conn.close()
                return False
            
            cursor.execute("SELECT COUNT(*) FROM soil_samples")
            soil_count = cursor.fetchone()[0]
            
            conn.close()
            
            return soil_count > 0
            
        except Exception as e:
            self.logger.pipeline_logger.logger.error(f"Error checking database existence: {e}")
            return False
    
    def clear_database(self) -> bool:
        """Clear all data from database tables."""
        try:
            self.logger.pipeline_logger.logger.info("Clearing existing database data...")
            
            if not self.connection:
                self.connection = sqlite3.connect(str(self.db_path))
            
            # Disable foreign key constraints temporarily
            self.connection.execute("PRAGMA foreign_keys = OFF")
            
            # Clear all tables
            tables = ['soil_samples', 'countries', 'clusters', 'analysis_results', 'pipeline_logs']
            for table in tables:
                self.connection.execute(f"DELETE FROM {table}")
                self.logger.pipeline_logger.logger.info(f"Cleared {table} table")
            
            # Reset auto-increment counters
            self.connection.execute("DELETE FROM sqlite_sequence")
            
            # Re-enable foreign key constraints
            self.connection.execute("PRAGMA foreign_keys = ON")
            
            self.connection.commit()
            
            self.logger.pipeline_logger.logger.info("Database cleared successfully")
            return True
            
        except Exception as e:
            self.logger.pipeline_logger.logger.error(f"Error clearing database: {e}")
            return False
    
    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.logger.log_connection("closed", str(self.db_path))
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def log_to_pipeline_logs(self, run_id, stage_name, log_level, message, duration_ms=None, record_count=None, error_details=None):
        """
        Insert a log record into the pipeline_logs table.
        """
        try:
            self.connection.execute(
                """
                INSERT INTO pipeline_logs (run_id, stage_name, log_level, message, duration_ms, record_count, error_details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, stage_name, log_level, message, duration_ms, record_count, error_details)
            )
            self.connection.commit()
        except Exception as e:
            # Fallback: print error if DB logging fails
            print(f"Failed to log to pipeline_logs: {e}")


if __name__ == "__main__":
    # Test the database manager
    from logger import setup_logging, DatabaseLogger
    
    # Setup logging
    pipeline_logger = setup_logging("db_test")
    db_logger = DatabaseLogger(pipeline_logger)
    
    # Test database manager
    with DatabaseManager("data/db/test.db", db_logger) as db:
        # Get database stats
        stats = db.get_database_stats()
        print(f"Database stats: {stats}")
    
    print("Database manager test completed.") 