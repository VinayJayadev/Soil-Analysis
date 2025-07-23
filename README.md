# 🌍 Geospatial Soil Analysis Pipeline

A comprehensive Python-based data pipeline for analyzing geospatial soil sample data across European countries. This project integrates with the Overpass API to fetch country boundaries, performs spatial analysis, implements K-means clustering, and generates statistical reports with visualizations.

## 🎯 Project Overview

This pipeline processes **7,012 soil samples** from European countries, associates them with geographic boundaries, performs clustering analysis, and generates comprehensive reports for soil carbon (SOC%) analysis.

### Key Features

- **7-Stage Pipeline**: Database initialization → Data loading → API integration → Spatial association → Clustering → Statistics → Reporting
- **Real Overpass API Integration**: Fetches European country boundaries dynamically
- **SQLite Database**: Normalized storage with spatial indexing
- **K-means Clustering**: 40 clusters across 8 countries for representative sampling
- **Comprehensive Logging**: Detailed execution logs and performance metrics
- **Visualization Suite**: Geographic maps, cluster analysis, and statistical plots
- **Production Ready**: Modular design with error handling and validation

## 📊 Results Summary

- **Total Samples**: 7,012 soil samples processed
- **Spatial Coverage**: 91.1% of samples successfully assigned to countries
- **Clusters Created**: 40 clusters across 8 European countries
- **Countries Covered**: Italia, España, France, Nederland, Polska, België, Deutschland, Česko
- **Average SOC%**: 3.53% (range: 0.41% - 30.81%)

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Internet connection (for Overpass API)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd seqana_swe_challenge
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the complete pipeline**
   ```bash
   python main.py
   ```

### Basic Usage

```bash
# Run with default settings (random sampling)
python main.py

# Run with clustering-based sampling
python main.py --sampling-method clustering

# Custom parameters
python main.py --sampling-method clustering --sample-size 100 --min-clusters 2 --max-clusters 10

# Check available options
python main.py --help
```

## 📁 Project Structure

```
seqana_swe_challenge/
├── main.py                     # Main pipeline runner
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── QUICK_START.md             # Quick start guide
├── IMPLEMENTATION_PLAN.md     # Implementation details
├── ARCHITECTURE.md            # System architecture
├── visualize_clusters.py      # Clustering visualization script
├── src/                       # Source code modules
│   ├── __init__.py
│   ├── database_manager.py    # SQLite database operations
│   ├── data_loader.py         # Soil sample data loading
│   ├── overpass_client.py     # Overpass API integration
│   ├── spatial_processor.py   # Spatial operations
│   ├── clustering_processor.py # K-means clustering
│   ├── statistics_calculator.py # Statistical analysis
│   └── logging_manager.py     # Logging configuration
├── data/                      # Data directory
│   ├── eu_wosis_points.fgb    # Input soil sample data
│   └── db/                    # SQLite database
│       └── soil_analysis.db
├── logs/                      # Execution logs
└── output/                    # Generated reports and visualizations
    ├── cluster_distribution.png
    ├── cluster_size_analysis.png
    ├── geographic_clusters.png
    ├── soc_analysis.png
    └── pipeline_report_*.txt
```

## 🔧 Configuration

### Environment Variables

```bash
export OVERPASS_API_URL="https://overpass-api.de/api/interpreter"
export OUTPUT_DIR="./output"
export LOG_LEVEL="INFO"
```

### Pipeline Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--sampling-method` | `random` | Sampling method: `random` or `clustering` |
| `--sample-size` | `100` | Number of samples per country |
| `--min-clusters` | `2` | Minimum clusters per country |
| `--max-clusters` | `10` | Maximum clusters per country |
| `--log-level` | `INFO` | Logging level |

## 📊 Database Schema

### Tables

1. **soil_samples**: Individual soil sample data
   - `id`, `raw_data_id`, `latitude`, `longitude`, `soc_percent`, `soc_method`, `top_depth_cm`, `bottom_depth_cm`, `sampling_date`, `lab_analysis_date`, `country_id`, `cluster_id`, `clay_fraction`, `created_at`

2. **countries**: European country boundaries
   - `id`, `name`, `iso_code`, `boundary_geojson`, `sample_count`, `created_at`

3. **clusters**: K-means clustering results
   - `id`, `country_id`, `cluster_number`, `center_latitude`, `center_longitude`, `sample_count`, `created_at`

4. **analysis_results**: Statistical analysis results
   - `id`, `country_id`, `sampling_method`, `sample_size`, `soc_mean`, `soc_variance`, `clay_fraction_mean`, `analysis_date`

5. **pipeline_logs**: Execution logs
   - `id`, `run_id`, `stage_name`, `log_level`, `message`, `timestamp`, `duration_ms`, `record_count`, `error_details`

## 🎨 Visualizations

The pipeline generates four key visualizations:

### 1. Cluster Distribution (`cluster_distribution.png`)
- Number of clusters by country
- Average samples per cluster by country

### 2. Cluster Size Analysis (`cluster_size_analysis.png`)
- Cluster size ranges by country
- Total samples vs cluster count relationship

### 3. Geographic Clusters (`geographic_clusters.png`)
- **Interactive map** with OpenStreetMap background
- Cluster centers plotted by country
- Country names and cluster numbers labeled

### 4. SOC Analysis (`soc_analysis.png`)
- Average SOC% by cluster
- SOC% variability by country

## 📈 Sample Output

### Pipeline Report
```
================================================================================
🎯 PIPELINE EXECUTION SUMMARY
================================================================================

📊 EXECUTION STATISTICS:
   • Total Duration: 45.2 seconds
   • Stages Completed: 7/7
   • Total Records Processed: 7,012
   • Success Rate: 100%

🌍 SPATIAL ANALYSIS:
   • Countries Processed: 8
   • Samples with Country Assignment: 6,389 (91.1%)
   • Samples Outside Boundaries: 623 (8.9%)

🎯 CLUSTERING RESULTS:
   • Total Clusters Created: 30
   • Average Clusters per Country: 3.8
   • Average Samples per Cluster: 251.1

📊 STATISTICAL ANALYSIS:
   • Sampling Method: clustering
   • Countries Analyzed: 8
   • Average SOC%: 3.53%
   • SOC% Range: 0.41% - 30.81%

🏆 TOP PERFORMING COUNTRIES:
   • Most Clusters: Italia (5 clusters)
   • Highest Average SOC%: Nederland (4.12%)
   • Most Samples: België (4,929 samples)
```

### Database Queries

```sql
-- View clustering results by country
SELECT 
    c.name as country_name,
    COUNT(cl.id) as cluster_count,
    AVG(cl.sample_count) as avg_samples_per_cluster
FROM clusters cl 
JOIN countries c ON cl.country_id = c.id 
GROUP BY c.name 
ORDER BY cluster_count DESC;

-- View statistical analysis results
SELECT 
    c.name as country_name,
    ar.sampling_method,
    ar.soc_mean,
    ar.soc_variance,
    ar.clay_fraction_mean
FROM analysis_results ar
JOIN countries c ON ar.country_id = c.id
ORDER BY ar.soc_mean DESC;
```

## 🔍 Key Insights

### Geographic Distribution
- **Southern Europe** (Italia, España) shows more diverse soil regions
- **Northern Europe** (Nederland, Deutschland) has moderate clustering
- **Small countries** (Česko) have limited spatial diversity

### Soil Carbon Patterns
- **High variability** in SOC% (0.41% to 30.81%) indicates diverse soil types
- **Regional patterns** exist within clusters
- **Carbon hotspots** and **carbon-poor regions** identified

### Clustering Quality
- **Good coverage** for most countries (91.1% of samples assigned)
- **Representative sampling** possible using cluster-based selection
- **Some countries** may benefit from parameter adjustments

## 🚨 Troubleshooting

### Common Issues

1. **Overpass API Timeout**
   ```bash
   # The pipeline includes retry logic, but if persistent:
   # Check internet connection and try again
   python main.py
   ```

2. **Database Locked**
   ```bash
   # Remove existing database to start fresh
   rm data/db/soil_analysis.db
   python main.py
   ```

3. **Memory Issues**
   ```bash
   # Reduce sample size for large datasets
   python main.py --sample-size 50
   ```

### Log Files

Check the `logs/` directory for detailed execution logs:
- `pipeline_YYYYMMDD_HHMMSS.log`: Main execution log
- `database_YYYYMMDD_HHMMSS.log`: Database operations
- `api_YYYYMMDD_HHMMSS.log`: API calls and responses

## 🔧 Development

### Adding New Features

1. **New Analysis Methods**: Extend `statistics_calculator.py`
2. **Additional Visualizations**: Add methods to `visualize_clusters.py`
3. **Database Schema Changes**: Update `database_manager.py`

### Testing

```bash
# Run individual components
python -c "from src.data_loader import SoilDataLoader; loader = SoilDataLoader('data/eu_wosis_points.fgb'); print('Data loading works!')"

# Test database operations
python -c "from src.database_manager import DatabaseManager; db = DatabaseManager(); print('Database connection works!')"
```

## 📚 Dependencies

### Core Dependencies
- `geopandas`: Geospatial data processing
- `pandas`: Data manipulation
- `numpy`: Numerical computing
- `scikit-learn`: Machine learning (K-means clustering)
- `requests`: HTTP requests for API calls
- `sqlite3`: Database operations
- `matplotlib`: Plotting and visualization
- `seaborn`: Statistical visualizations
- `contextily`: Map backgrounds for geographic plots

### Optional Dependencies
- `folium`: Interactive maps (for future enhancements)
- `plotly`: Interactive visualizations (for future enhancements)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request


## 🙏 Acknowledgments

- **Overpass API** for providing European country boundary data
- **WoSIS** for the soil sample dataset
- **OpenStreetMap** for map tile data used in visualizations

## 🚀 Architecture Evolution & Future Directions

- **Multi-Tenancy:**
  - Evolve the pipeline to support multiple clients, each with isolated data and results. This enables SaaS-style deployments and secure, scalable usage by different organizations.

- **Machine Learning Integration:**
  - Integrate advanced ML models for predictive soil property estimation, anomaly detection, or automated clustering. This can enhance the value of the analysis and enable new features such as soil health prediction.

- **API-Driven Design:**
  - Expose the pipeline as a RESTful API, allowing clients to submit custom geospatial areas, trigger analyses, and retrieve results programmatically. This supports real-time, on-demand analytics and easy integration with other systems.

### Supporting Client-Submitted Geospatial Areas

- **Custom Area Submission:**
  - Extend the pipeline to accept user-defined polygons (e.g., GeoJSON) via an API or web interface.
- **Dynamic Spatial Association:**
  - Submitted areas are spatially joined with the soil sample database to extract relevant samples for analysis.
- **On-Demand Analysis:**
  - The system runs clustering, sampling, and statistics for the user’s area, returning results and visualizations.
- **Use Cases:**
  - Enables tailored soil analysis for farms, research plots, or administrative regions beyond country boundaries.

- These directions ensure the pipeline remains scalable, flexible, and ready for future geospatial analytics needs. 
---

## 📞 Support

For questions or issues:
1. Check the troubleshooting section above
2. Review the logs in the `logs/` directory
3. Open an issue with detailed error information

**Happy soil analyzing! 🌱** 

## ⏰ Time Management & Future Priorities

**Time-boxed Implementation:**  
This project was completed within a strict 4-hour time limit.

**Time Spent:**  
- Total time spent: **4 hours** (including design, coding, testing, and documentation).

**If Given More Time, I Would Prioritize:**
- **Automated Testing:** Add comprehensive unit and integration tests for all modules.
- **User Interface:** Develop a simple web or API interface for easier user interaction.
- **Performance Optimization:** Profile and optimize spatial joins and clustering for very large datasets.
- **Advanced Visualizations:** Add interactive dashboards and more granular spatial plots.
- **Continuous Integration:** Set up CI/CD pipelines for automated testing and deployment. 

## Docker Usage

You can run the soil analysis pipeline using Docker. 

### Build the Docker Image

From the project root directory, run:

```sh
docker build -t soil-analysis .
```

### Run the Pipeline in a Container

To run the pipeline with default settings:

```sh
docker run --rm soil-analysis
```

#### (Optional) Mount Data and Output Directories

To persist input and output files between runs, mount your local `data` and `output` directories:

```sh
docker run --rm -v "${PWD}/data:/app/data" -v "${PWD}/output:/app/output" soil-analysis
```

#### (Optional) Pass Custom Arguments

You can override the default arguments in `main.py`:

```sh
docker run --rm soil-analysis --data-file data/eu_wosis_points.fgb --output-dir output
```

Or, with volume mounts:

```sh
docker run --rm -v "${PWD}/data:/app/data" -v "${PWD}/output:/app/output" soil-analysis --data-file data/eu_wosis_points.fgb --output-dir output
```

---
