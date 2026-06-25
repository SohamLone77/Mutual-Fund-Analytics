#!/usr/bin/env python
"""
Live NAV Fetch - Fetch mutual fund NAV data from API
Day 1 - Mutual Fund Analytics Project
"""

import requests
import pandas as pd
import json
import os
from datetime import datetime
import time

class NAVFetcher:
    """Fetch live NAV data from mfapi.in"""
    
    def __init__(self):
        self.base_url = "https://api.mfapi.in/mf"
        self.raw_data_path = 'data/raw'
        self.nav_data = {}
        
        # Key schemes to fetch
        self.schemes = {
            '125497': 'HDFC_Top_100_Direct',
            '119551': 'SBI_Bluechip',
            '120503': 'ICICI_Bluechip',
            '118632': 'Nippon_Large_Cap',
            '119092': 'Axis_Bluechip',
            '120841': 'Kotak_Bluechip'
        }
        
        os.makedirs(self.raw_data_path, exist_ok=True)
    
    def fetch_scheme_nav(self, scheme_code):
        """Fetch NAV data for a single scheme"""
        
        try:
            url = f"{self.base_url}/{scheme_code}"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract metadata
                meta = data.get('meta', {})
                nav_data = data.get('data', [])
                
                return {
                    'meta': meta,
                    'nav_data': nav_data,
                    'scheme_code': scheme_code
                }
            else:
                print(f"❌ Error {response.status_code} for scheme {scheme_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed for {scheme_code}: {e}")
            return None
    
    def fetch_all_schemes(self):
        """Fetch NAV for all configured schemes"""
        
        print("📡 Fetching live NAV data...")
        print("="*60)
        
        for code, name in self.schemes.items():
            print(f"\n🔄 Fetching: {name} (Code: {code})")
            
            result = self.fetch_scheme_nav(code)
            
            if result:
                self.nav_data[code] = result
                
                # Save raw JSON
                self._save_raw_json(code, result)
                
                # Save as CSV
                self._convert_to_csv(code, result)
                
                print(f"   ✅ Fetched {len(result['nav_data'])} NAV entries")
            else:
                print(f"   ⚠️  Failed to fetch {name}")
            
            # Rate limiting - be respectful to API
            time.sleep(1)
        
        print("\n" + "="*60)
        print(f"✅ Fetched {len(self.nav_data)} out of {len(self.schemes)} schemes")
    
    def _save_raw_json(self, code, data):
        """Save raw JSON response"""
        filename = f"{self.raw_data_path}/nav_{code}_{datetime.now().strftime('%Y%m%d')}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"   📁 JSON saved: {os.path.basename(filename)}")
    
    def _convert_to_csv(self, code, data):
        """Convert NAV data to CSV"""
        
        if not data['nav_data']:
            print("   ⚠️  No NAV data to convert")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(data['nav_data'])
        
        # Clean and convert types
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
        df['nav'] = pd.to_numeric(df['nav'])
        
        # Add metadata columns
        meta = data['meta']
        df['scheme_code'] = code
        df['scheme_name'] = meta.get('scheme_name', '')
        df['fund_house'] = meta.get('fund_house', '')
        
        # Sort by date
        df = df.sort_values('date')
        
        # Save to CSV
        filename = f"{self.raw_data_path}/nav_{code}_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        
        print(f"   📁 CSV saved: {os.path.basename(filename)}")
        print(f"   📊 Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    
    def get_nav_summary(self):
        """Get summary of fetched NAV data"""
        
        summary = []
        for code, data in self.nav_data.items():
            meta = data.get('meta', {})
            nav_data = data.get('nav_data', [])
            
            if nav_data:
                df = pd.DataFrame(nav_data)
                df['nav'] = pd.to_numeric(df['nav'])
                
                summary.append({
                    'scheme_code': code,
                    'scheme_name': meta.get('scheme_name', ''),
                    'fund_house': meta.get('fund_house', ''),
                    'total_entries': len(nav_data),
                    'latest_nav': df.iloc[-1]['nav'],
                    'latest_date': df.iloc[-1]['date'],
                    'min_nav': df['nav'].min(),
                    'max_nav': df['nav'].max()
                })
        
        return pd.DataFrame(summary)

# ========== MAIN EXECUTION ==========

def main():
    """Main execution function"""
    
    print("🚀 Starting Live NAV Fetch Process...")
    print("="*60)
    
    # Initialize fetcher
    fetcher = NAVFetcher()
    
    # Fetch all schemes
    fetcher.fetch_all_schemes()
    
    # Print summary
    if fetcher.nav_data:
        print("\n📊 NAV Fetch Summary:")
        print("-"*60)
        summary_df = fetcher.get_nav_summary()
        print(summary_df.to_string(index=False))
        
        # Save summary
        summary_df.to_csv('reports/nav_fetch_summary.csv', index=False)
        print(f"\n✅ Summary saved to: reports/nav_fetch_summary.csv")
    
    print("\n✅ Live NAV Fetch Complete!")

if __name__ == "__main__":
    main()