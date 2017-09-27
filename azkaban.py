import urllib2, json, urllib, time
import requests
import json
from utils import *

user = 'azkaban'
pwd = '15yinker@bj'
host = 'http://10.2.19.62:8081'


class CookiesFetcher:
    def __init__(self, user, pwd):
        self.login_data = {'action': 'login', 'username': user, 'password': pwd}
        resp = requests.post("http://10.2.19.62:8081", data=self.login_data)
        self.cookies = resp.cookies

    def get_cookies(self):
        return self.cookies

    def refresh(self):
        resp = requests.post("http://10.2.19.62:8081", data=self.login_data)
        self.cookies = resp.cookies
        return self.cookies


class Project:
    def __init__(self, project, description, cookies_fetcher):
        self.project = project
        self.description = description
        self.cookies_fetcher = cookies_fetcher

    def create_prj(self):
        create_data = {
            'name': self.project,
            'description': self.description
        }
        resp = requests.post("http://10.2.19.62:8081/manager?action=create", data=create_data,
                             cookies=self.cookies_fetcher.get_cookies())
        if resp.status_code != 200:
            raise Exception('Error happened when creating project {project} to azkaban'.format(project=self.project))
        print 'project {project} creatd : {status}'.format(project=self.project,
                                                           status=json.loads(resp.content)['status'])
        return self

    def upload_zip(self, zipfile):
        files = {'file': ('xxx.ip', open(zipfile, 'rb'), 'application/zip')}
        upload_data = {
            'project': self.project,
            'ajax': 'upload',

        }
        resp = requests.post("http://10.2.19.62:8081/manager", data=upload_data,
                             cookies=self.cookies_fetcher.get_cookies(),
                             files=files)
        if resp.status_code != 200:
            raise Exception('Error happened when upload flow {flow_name} to azkaban'.format(flow_name=zipfile))
        print self.project

    def fetch_flow(self):
        flows_resp = requests.get(
            'http://10.2.19.62:8081/manager?ajax=fetchprojectflows&project={project}'.format(project=self.project),
            cookies=self.cookies_fetcher.get_cookies())
        if flows_resp.status_code != 200:
            raise Exception('Error happened when fetch flow from {project} in azkaban'.format(project=self.project))
        flows = json.loads(flows_resp.content)['flows']
        for flow in flows:
            yield Flow(self.project, flow['flowId'], self.cookies_fetcher)


class Flow:
    def __init__(self, project, flowId, cookies_fetcher):
        self.project = project
        self.flowId = flowId
        self.cookies_fetcher = cookies_fetcher

    def execute(self):
        '''
        Execute specified flow.
        :return: Running flow execution id
        '''
        flows_resp = requests.get(
            'http://10.2.19.62:8081/executor?ajax=executeFlow&project={project}&flow={flow}'.format(
                project=self.project,
                flow=self.flowId),
            cookies=self.cookies_fetcher.get_cookies())
        if flows_resp.status_code != 200:
            raise Exception('Error happened when fetch flow from {flow} in azkaban'.format(flow=self.flowId))
        exec_id = json.loads(flows_resp.content)['execid']
        return FlowExecution(self.project, self.flowId, exec_id, self.cookies_fetcher)


class FlowExecution:
    job_status_dict = dict()
    flow_timeout = 180

    def __init__(self, project, flowId, exec_id, cookies_fetcher):
        self.project = project
        self.flowId = flowId
        self.exec_id = exec_id
        self.cookies_fetcher = cookies_fetcher

    def resume_flow(self):
        target = '%s/executor?ajax=executeFlow&project=%s&flow=%s&disabled=%s' % (
            host, self.project, self.flowId, get_str_set(self.job_status_dict.get('SUCCEEDED', set())))
        resp = requests.get(target, cookies=self.cookies_fetcher.get_cookies())
        contents = resp.content
        new_exec_id = json.loads(contents)['execid']
        print('old exec_id {old} to new one {new}'.format(old=self.exec_id, new=new_exec_id))
        self.exec_id = new_exec_id

    def handle_timeout(self):
        '''
        If the execution has expired specified period, kill it and resume the flow.
        This is used to deal with some hang problems.
        :param exec_id:
        :return:
        '''
        while True:
            result = self.get_flow_exec_info()
            self.refresh_flow_execution()
            start_time = result['startTime']
            start_time /= 1000
            if result['status'] == 'KILLED':
                print("{execid} has been killed.".format(execid=self.exec_id))
                break
            elif result['status'] == 'SUCCEEDED':
                print("{execid} has been SUCCEEDED.".format(execid=self.exec_id))
                break
            elif result['status'] == 'FAILED':
                print("{execid} has been FAILED.".format(execid=self.exec_id))
                break
            if int(time.time()) - start_time > 60 * self.flow_timeout and result['endTime'] == -1:
                print('reached timeout threshold \n')
                self.cancel()
                time.sleep(60)
                self.resume_flow(result['project'], result['flow'])
            time.sleep(60 * 10 * 1000)

    def refresh_flow_execution(self):
        '''
        Refresh job status to the flow execution dict.
        :param exec_id:
        :return:
        '''
        result = self.get_flow_exec_info()
        for dd in result['nodes']:
            cu = self.job_status_dict.get(dd['status'], set())
            cu.add(dd['id'])
            self.job_status_dict[dd['status']] = cu
        for k, v in self.job_status_dict.items():
            print('%s  status: %s : %d/%d \n' % (get_current_timekey(), k, len(v), len(result['nodes'])))

    def get_flow_exec_info(self):
        '''
        Get the flow execution json info.
        :param exec_id:
        :return:
        '''
        target = '%s/executor?ajax=fetchexecflow&execid=%s' % (host, self.exec_id)
        resp = requests.get(target, cookies=self.cookies_fetcher.get_cookies())
        return json.loads(resp.content)

    def cancel(self, cookies):
        target = '%s/executor?ajax=cancelFlow&execid=%s' % (host, self.exec_id)
        resp = requests.get(target, cookies=self.cookies_fetcher.get_cookies())
        if resp.getcode() != 200:
            print(resp.read() + '\n')