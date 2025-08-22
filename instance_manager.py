import boto3
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class LightsailInstanceManager:
    def __init__(self):
        self.api_delay = float(os.getenv('API_DELAY_SECONDS', '0.12'))
    
    def load_alert_instances(self, alert_level):
        """加载指定级别的告警实例"""
        filename = f'alert_{alert_level}_instances.json'
        
        if not os.path.exists(filename):
            print(f"告警文件 {filename} 不存在")
            return []
        
        try:
            with open(filename, 'r') as f:
                instances = json.load(f)
            print(f"加载 {alert_level} 级别告警实例: {len(instances)} 个")
            return instances
        except Exception as e:
            print(f"加载告警文件失败: {e}")
            return []
    
    def stop_instances(self, instances, dry_run=True):
        """批量停止实例"""
        if not instances:
            print("没有需要停止的实例")
            return
        
        print(f"{'[模拟模式]' if dry_run else '[执行模式]'} 准备停止 {len(instances)} 个实例:")
        
        stopped_count = 0
        failed_count = 0
        
        for instance_info in instances:
            instance_name = instance_info['instance_name']
            region = instance_info['region']
            usage_percent = instance_info['usage_percent']
            
            try:
                if not dry_run:
                    lightsail = boto3.client('lightsail', region_name=region)
                    time.sleep(self.api_delay)
                    
                    response = lightsail.stop_instance(instanceName=instance_name)
                    print(f"✓ 已停止: {instance_name} ({region}) - 使用率: {usage_percent}%")
                    stopped_count += 1
                else:
                    print(f"○ 模拟停止: {instance_name} ({region}) - 使用率: {usage_percent}%")
                    stopped_count += 1
                
            except Exception as e:
                print(f"✗ 停止失败: {instance_name} ({region}) - 错误: {e}")
                failed_count += 1
        
        print(f"\n操作完成: 成功 {stopped_count} 个, 失败 {failed_count} 个")
        
        # 记录操作日志
        self.log_operation(instances, dry_run, stopped_count, failed_count)
    
    def start_instances(self, instances, dry_run=True):
        """批量启动实例"""
        if not instances:
            print("没有需要启动的实例")
            return
        
        print(f"{'[模拟模式]' if dry_run else '[执行模式]'} 准备启动 {len(instances)} 个实例:")
        
        started_count = 0
        failed_count = 0
        
        for instance_info in instances:
            instance_name = instance_info['instance_name']
            region = instance_info['region']
            
            try:
                if not dry_run:
                    lightsail = boto3.client('lightsail', region_name=region)
                    time.sleep(self.api_delay)
                    
                    response = lightsail.start_instance(instanceName=instance_name)
                    print(f"✓ 已启动: {instance_name} ({region})")
                    started_count += 1
                else:
                    print(f"○ 模拟启动: {instance_name} ({region})")
                    started_count += 1
                
            except Exception as e:
                print(f"✗ 启动失败: {instance_name} ({region}) - 错误: {e}")
                failed_count += 1
        
        print(f"\n操作完成: 成功 {started_count} 个, 失败 {failed_count} 个")
    
    def log_operation(self, instances, dry_run, success_count, failed_count):
        """记录操作日志"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'operation': 'stop_instances',
            'dry_run': dry_run,
            'total_instances': len(instances),
            'success_count': success_count,
            'failed_count': failed_count,
            'instances': [{'name': inst['instance_name'], 'region': inst['region']} for inst in instances]
        }
        
        log_file = 'instance_operations.log'
        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(f"写入日志失败: {e}")

def main():
    manager = LightsailInstanceManager()
    
    print("=== Lightsail实例批量管理工具 ===")
    print("1. 停止紧急告警实例 (critical)")
    print("2. 停止高级告警实例 (high)")  
    print("3. 停止中级告警实例 (medium)")
    print("4. 启动指定级别实例")
    print("5. 查看告警实例列表")
    
    choice = input("\n请选择操作 (1-5): ").strip()
    
    if choice in ['1', '2', '3']:
        level_map = {'1': 'critical', '2': 'high', '3': 'medium'}
        alert_level = level_map[choice]
        
        instances = manager.load_alert_instances(alert_level)
        if not instances:
            return
        
        print(f"\n找到 {len(instances)} 个 {alert_level} 级别告警实例:")
        for inst in instances:
            print(f"  {inst['instance_name']} ({inst['region']}) - {inst['usage_percent']}%")
        
        # 确认操作
        dry_run = input("\n是否先进行模拟运行? (y/n): ").lower() == 'y'
        
        if dry_run:
            manager.stop_instances(instances, dry_run=True)
            
            confirm = input("\n模拟完成，是否执行实际停止操作? (yes/no): ").lower()
            if confirm == 'yes':
                manager.stop_instances(instances, dry_run=False)
        else:
            confirm = input(f"\n确认停止 {len(instances)} 个实例? (yes/no): ").lower()
            if confirm == 'yes':
                manager.stop_instances(instances, dry_run=False)
    
    elif choice == '4':
        level = input("请输入告警级别 (critical/high/medium): ").strip()
        instances = manager.load_alert_instances(level)
        if instances:
            dry_run = input("是否模拟运行? (y/n): ").lower() == 'y'
            manager.start_instances(instances, dry_run)
    
    elif choice == '5':
        for level in ['critical', 'high', 'medium']:
            instances = manager.load_alert_instances(level)
            if instances:
                print(f"\n{level.upper()} 级别告警实例 ({len(instances)} 个):")
                for inst in instances:
                    print(f"  {inst['instance_name']} ({inst['region']}) - {inst['usage_percent']}%")
    
    else:
        print("无效选择")

if __name__ == "__main__":
    main()