#!/usr/bin/env python3
"""
性能测试脚本 - 验证优化后的监控系统性能
"""

import time
import json
from datetime import datetime
from intelligent_monitoring import intelligent_quota_monitoring

def performance_test():
    """性能测试"""
    print("=== Lightsail监控系统性能测试 ===")
    
    # 记录开始时间
    start_time = time.time()
    start_datetime = datetime.now()
    
    print(f"测试开始时间: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 执行监控
        alerts = intelligent_quota_monitoring()
        
        # 记录结束时间
        end_time = time.time()
        end_datetime = datetime.now()
        total_duration = end_time - start_time
        
        print(f"\n=== 性能测试结果 ===")
        print(f"测试结束时间: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总执行时间: {total_duration:.2f} 秒 ({total_duration/60:.1f} 分钟)")
        print(f"发现告警数量: {len(alerts) if alerts else 0}")
        
        # 保存性能报告
        performance_report = {
            'test_datetime': start_datetime.isoformat(),
            'duration_seconds': round(total_duration, 2),
            'duration_minutes': round(total_duration/60, 1),
            'alerts_found': len(alerts) if alerts else 0,
            'status': 'completed'
        }
        
        with open('performance_test_report.json', 'w') as f:
            json.dump(performance_report, f, indent=2)
        
        print(f"\n性能报告已保存到: performance_test_report.json")
        
        # 性能评估
        if total_duration < 300:  # 5分钟
            print("✅ 性能优秀: 执行时间 < 5分钟")
        elif total_duration < 900:  # 15分钟
            print("⚠️  性能良好: 执行时间 < 15分钟")
        else:
            print("❌ 性能需要优化: 执行时间 > 15分钟")
        
        return performance_report
        
    except Exception as e:
        end_time = time.time()
        total_duration = end_time - start_time
        
        print(f"\n❌ 测试失败: {e}")
        print(f"失败前执行时间: {total_duration:.2f} 秒")
        
        error_report = {
            'test_datetime': start_datetime.isoformat(),
            'duration_seconds': round(total_duration, 2),
            'error': str(e),
            'status': 'failed'
        }
        
        with open('performance_test_report.json', 'w') as f:
            json.dump(error_report, f, indent=2)
        
        return error_report

if __name__ == "__main__":
    performance_test()