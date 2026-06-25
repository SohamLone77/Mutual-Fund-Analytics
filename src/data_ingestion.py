#!/usr/bin/env python
"""
Data Ingestion Module - Load and validate all CSV datasets
Day 1 - Mutual Fund Analytics Project
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
import glob
import json

class DataIngestion:
    """Handles loading and validating CSV data"""
    
    def __init__(self):
        self.raw_data_path = 'data/raw'
        self.processed_data_path = 'data/processed'
        self.datasets = {}
        self.quality_report = {}
        
        # Create directories if they don't exist
        os.makedirs(self.raw_data_path, exist_ok=True)
        os.makedirs(self.processed_data_path, exist_ok=True)
        
    def load_all_datasets(self):
        """Load all CSV files from raw data directory"""
        
        csv_files = glob.glob(os.path.join(self.raw_data_path, '*.csv'))
        
        if not csv_files:
            print("⚠️  No CSV files found in data/raw/")
            print("   Please place your 10 CSV files in data/raw/")
            return
        
        print(f"📁 Found {len(csv_files)} CSV files")
        print("="*60)
        
        for file_path in csv_files:
            filename = os.path.basename(file_path)
            try:
                # Load CSV
                df = pd.read_csv(file_path)
                
                # Store in datasets dict
                key = filename.replace('.csv', '')
                self.datasets[key] = df
                
                # Print information
                self._print_dataset_info(filename, df)
                
                # Collect quality metrics
                self._collect_quality_metrics(key, df)
                
            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")
        
        return self.datasets
    
    def _print_dataset_info(self, filename, df):
        """Print dataset information"""
        print(f"\n📊 Dataset: {filename}")
        print(f"   Shape: {df.shape[0]} rows x {df.shape[1]} columns")
        print(f"   Columns: {', '.join(df.columns.tolist()[:5])}{'...' if len(df.columns) > 5 else ''}")
        
        # Check for missing values
        missing = df.isnull().sum().sum()
        if missing > 0:
            print(f"   ⚠️  Missing values: {missing}")
        
        # Check data types
        print(f"   Data types: {', '.join(str(dt) for dt in df.dtypes.unique())}")
        
        # Show sample
        print("\n   First 2 rows:")
        print(df.head(2).to_string(index=False)[:200] + "...")
    
    def _collect_quality_metrics(self, key, df):
        """Collect data quality metrics"""
        metrics = {
            'rows': len(df),
            'columns': len(df.columns),
            'missing_values': df.isnull().sum().sum(),
            'duplicate_rows': df.duplicated().sum(),
            'numeric_cols': len(df.select_dtypes(include=[np.number]).columns),
            'categorical_cols': len(df.select_dtypes(include=['object']).columns),
            'memory_usage': df.memory_usage(deep=True).sum() / 1024**2  # MB
        }
        
        # Check for date columns
        date_cols = []
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    pd.to_datetime(df[col])
                    date_cols.append(col)
                except:
                    pass
        metrics['date_cols'] = date_cols
        
        self.quality_report[key] = metrics
    
    def generate_quality_summary(self):
        """Generate a data quality summary report"""
        
        if not self.quality_report:
            print("⚠️  No datasets loaded. Run load_all_datasets() first.")
            return
        
        print("\n" + "="*60)
        print("📊 DATA QUALITY SUMMARY REPORT")
        print("="*60)
        
        total_rows = 0
        total_missing = 0
        
        for dataset, metrics in self.quality_report.items():
            print(f"\n📁 {dataset}:")
            print(f"   Rows: {metrics['rows']:,}")
            print(f"   Columns: {metrics['columns']}")
            print(f"   Missing values: {metrics['missing_values']:,}")
            print(f"   Duplicate rows: {metrics['duplicate_rows']:,}")
            print(f"   Numeric columns: {metrics['numeric_cols']}")
            print(f"   Categorical columns: {metrics['categorical_cols']}")
            if metrics['date_cols']:
                print(f"   Date columns: {', '.join(metrics['date_cols'])}")
            print(f"   Memory usage: {metrics['memory_usage']:.2f} MB")
            
            total_rows += metrics['rows']
            total_missing += metrics['missing_values']
        
        # Summary statistics
        print("\n" + "-"*60)
        print(f"📊 TOTAL SUMMARY:")
        print(f"   Total datasets: {len(self.quality_report)}")
        print(f"   Total rows across all datasets: {total_rows:,}")
        print(f"   Total missing values: {total_missing:,}")
        print("="*60)
        
        # Save summary
        self._save_quality_report()
    
    def _save_quality_report(self):
        """Save quality report to file"""
        report_path = 'reports/data_quality_report.txt'
        os.makedirs('reports', exist_ok=True)
        
        with open(report_path, 'w') as f:
            f.write("="*60 + "\n")
            f.write("DATA QUALITY SUMMARY REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            for dataset, metrics in self.quality_report.items():
                f.write(f"\n {dataset}:\n")
                for key, value in metrics.items():
                    f.write(f"   {key}: {value}\n")
        
        print(f"\n✅ Quality report saved to: {report_path}")
    
    def get_dataframe(self, name):
        """Get a specific dataset by name"""
        return self.datasets.get(name)

# ========== MAIN EXECUTION ==========

def main():
    """Main execution function"""
    
    print("🚀 Starting Data Ingestion Process...")
    print("="*60)
    
    # Initialize ingestion
    ingestion = DataIngestion()
    
    # Load all datasets
    ingestion.load_all_datasets()
    
    # Generate quality summary
    ingestion.generate_quality_summary()
    
    print("\n✅ Data Ingestion Complete!")

if __name__ == "__main__":
    main()