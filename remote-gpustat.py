import os
import xml.etree.ElementTree as ET
import paramiko
import re
import time
from blessings import Terminal
import atexit
import argparse

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--servers', default=None,type=str,required=False,
                    help='{username}@{ip}的形式来表示主机,多个主机之间用逗号分隔,必须保证已经免密钥')
parser.add_argument('--config_file',default="server_list",type=str,required=False,
                    help='配置文件的位置,一行一个主机地址')


class GPUHost:
    def __init__(self, username, ip):
        self._address = ip
        self._ssh_cmd = "ssh %s 'nvidia-smi -q -x'" % ip
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh.connect(hostname=ip,
                          port=22,
                          username=username)

    def get_gpu_info(self):
        gpu_info_xml = self._run_command('nvidia-smi -q -x')
        gpu_info_xml = ET.fromstring(gpu_info_xml)
        gpu_infos = self._parse_gpu_info(gpu_info_xml)

        return gpu_infos

    def _run_command(self, command):
        stdin, stdout, stderr = self._ssh.exec_command(command)
        rs = stdout.read().decode()
        return rs

    def _parse_gpu_info(self, gpu_info_xml):
        user_pids = self._get_user_pid_info()
        gpus = gpu_info_xml.findall('gpu')

        gpu_infos = []
        for idx, gpu in enumerate(gpus):
            model = gpu.find('product_name').text
            processes = gpu.findall('processes')[0]
            fan_speed = gpu.findall('fan_speed')[0].text
            memory_total = gpu.find('fb_memory_usage').find('total').text
            memory_used = gpu.find('fb_memory_usage').find('used').text
            temperature = gpu.find('temperature').find('gpu_temp').text

            pids = []
            for p in processes:
                pid = {}
                pid['pid'] = p.find('pid').text
                pid['used_momery'] = p.find('used_memory').text
                pid['user'] = user_pids[pid['pid']]['user']
                pid['uptime'] = user_pids[pid['pid']]['uptime']
                pids.append(pid)

            gpu_infos.append({'idx': idx, 'model': model,
                              'mem_total': memory_total, 'mem_used': memory_used, 'temp': temperature,
                              'fan_speed': fan_speed, 'pids': pids})
        return gpu_infos

    def _get_user_pid_info(self):
        user_pids = {}
        ps_info = self._run_command("ps -ef").split('\n')
        for p in ps_info[1:]:
            if p == '':
                continue
            p = re.split(' +', p)
            user_pids[p[1]] = {
                'user': p[0],
                'uptime': p[6]
            }
        return user_pids

    def disconnect(self):
        self._ssh.close()


class GPUStat:
    def __init__(self, server_list):
        self.server_list = server_list
        self.gpu_hosts = []
        for server in server_list:
            gpu = GPUHost(server['username'], server['ip'])
            self.gpu_hosts.append(gpu)

        print('find %d gpu hosts' % len(self.gpu_hosts))

        self.t = Terminal()
        atexit.register(self.exit)

    # disconnect
    def exit(self):
        for gpu in self.gpu_hosts:
            gpu.disconnect()
        print("exit success")

    def get_remote_gpu_stats(self):
        gpu_stats = {gpu._address: gpu.get_gpu_info()
                     for gpu in self.gpu_hosts}
        return gpu_stats

    def print_stats(self):
        gpu_stats = self.get_remote_gpu_stats()
        # with self.t.fullscreen():
        now = time.asctime(time.localtime(time.time()))
        print("%s | found %d gpu hosts" % (now, len(self.gpu_hosts)))
        for ip in gpu_stats:
            self.print_one_gpu(ip, gpu_stats[ip])

    def print_one_gpu(self, ip, gpu_stat):
        print(('\n{t.bold}{t.black}{t.on_white}%s{t.normal}' %
               (ip)) .format(t=self.t))
        print(
            self.t.bold('-----------------------------------------------------------------------------'))
        for gpu in gpu_stat:
            print(('{t.bold}{t.magenta}%d {t.white}|{t.blue} %s {t.white}| {t.bold}{t.red}%s{t.white}/{t.green}%s{t.white} | {t.white} fan: %s (%s) | process: %d{t.normal}' %
                   (gpu['idx'], gpu['model'], gpu['mem_used'], gpu['mem_total'], gpu['fan_speed'], gpu['temp'], len(gpu['pids']))).format(t=self.t))
            for id, pid in enumerate(gpu['pids']):
                print(("{t.bold}{t.cyan}[%d]{t.yellow}%s\t{t.white}%s\t{t.white}%s\t{t.white}%s{t.normal}" % (id, pid['user'],
                                                                                                              pid['pid'], pid['used_momery'], pid['uptime'])).format(t=self.t))
            print(
                self.t.bold('-----------------------------------------------------------------------------'))


def get_server_list(path="./server_list"):
    server_list = []
    with open(path, 'r') as f:
        for line in f:
            username, ip = line.strip().split("@")
            server_list.append({
                'username': username,
                'ip': ip
            })

    return server_list


if __name__ == '__main__':
    args = parser.parse_args()
    server_list = []
    if args.servers==None and args.config_file==None:
        print("必须设置servers参数或者指定config配置文件")
    elif args.servers=='' and args.config_file=='':
        print('配置内容不能为空')
    elif args.servers!=None:
        server_list = [{'username':x.split('@')[0],'ip':x.split('@')[1]} for x in args.servers.strip().split(',')]
    elif os.path.exists(args.config_file)==False:
        print("配置文件必须存在")
    else:
        server_list = get_server_list(args.config_file)

    if len(server_list)!=0:
        main = GPUStat(server_list)
        main.print_stats()
