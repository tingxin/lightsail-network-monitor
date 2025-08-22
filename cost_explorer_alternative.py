import boto3
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()

def get_lightsail_costs():
    """使用Cost Explorer获取Lightsail数据传输成本（避免大量API调用）"""
    ce = boto3.client('ce', region_name='us-east-1')
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    analysis_days = int(os.getenv('COST_ANALYSIS_DAYS', '30'))
    start_date = (datetime.now() - timedelta(days=analysis_days)).strftime('%Y-%m-%d')
    
    try:
        # 获取Lightsail数据传输成本
        response = ce.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='DAILY',
            Metrics=['BlendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'REGION'},
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}
            ],
            Filter={
                'And': [
                    {'Dimensions': {'Key': 'SERVICE', 'Values': ['Amazon Lightsail']}},
                    {'Dimensions': {'Key': 'USAGE_TYPE_GROUP', 'Values': ['Lightsail-DataTransfer']}}
                ]
            }
        )
        
        # 解析数据传输量
        total_gb = 0
        by_region = {}
        
        for result in response['ResultsByTime']:
            for group in result['Groups']:
                region = group['Keys'][0]
                usage_type = group['Keys'][1]
                
                if 'DataTransfer-Out' in usage_type:
                    usage_gb = float(group['Metrics']['UsageQuantity']['Amount'])
                    total_gb += usage_gb
                    
                    if region not in by_region:
                        by_region[region] = 0
                    by_region[region] += usage_gb
        
        return {
            'total_data_transfer_gb': total_gb,
            'by_region': by_region,
            'period': f"{start_date} to {end_date}",
            'analysis_days': analysis_days
        }
        
    except Exception as e:
        print(f"Cost Explorer错误: {e}")
        return None

def hybrid_monitoring():
    """混合监控方案：Cost Explorer + 少量采样"""
    print("=== 基于成本数据的流量分析 ===")
    cost_data = get_lightsail_costs()
    
    if cost_data:
        analysis_days = cost_data['analysis_days']
        print(f"过去{analysis_days}天总数据传输: {cost_data['total_data_transfer_gb']:.2f} GB")
        print("按Region分布:")
        for region, gb in cost_data['by_region'].items():
            print(f"  {region}: {gb:.2f} GB")
        
        # 估算当前月流量
        days_in_month = datetime.now().day
        estimated_monthly = cost_data['total_data_transfer_gb'] * (analysis_days / days_in_month)
        print(f"估算本月总流量: {estimated_monthly:.2f} GB")
        
        return cost_data
    
    return None

if __name__ == "__main__":
    hybrid_monitoring()