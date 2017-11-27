# -*- coding: utf-8 -*-

import argparse
import requests
import json
import time

project_list = []
cookie = ''
base_url = ''

def init():
    '''
    初始化相关参数
    :return: None
    '''
    parser = argparse.ArgumentParser(description="获取Java项目的依赖信息.")
    parser.add_argument("-p", "--project", type=str, metavar="project", required=True,
                        help="Stash的项目列表，以','进行分割不同项目.")
    parser.add_argument("-c", "--cookie", metavar="cookie", required=True,
                        help="访问Stash的验证信息，一般储存在Cookie中.")
    parser.add_argument("-l", "--url", metavar="base url", required=True,
                        help="Stash的基本地址，展示Project的地址.")
    args = parser.parse_args()

    global project_list, cookie, base_url
    projects = args.project
    for project in projects.split(','):
        if project.strip() != '':
            project_list.append(project)
    cookie = args.cookie
    base_url = args.url

def get_repositories(project_name):
    '''
    该方法用于获取Project中的所有Repository
    :param project_name: project名称，方便构造URL名称
    :return:
    '''
    limit_num = 10000
    repositories_dict = {}
    headers = {
        'Cookie': cookie
    }
    url = base_url + 'projects/' + project_name + '/repos?limit=' + str(limit_num)
    response = requests.get(url=url, headers=headers).json()
    repositories = response.get('values')
    for repository in repositories:
        try:
            name = repository.get('name')
            language = repository.get('language')
            link_url = repository.get('link')['url']
            owner_dict = repository.get('owner')
            if owner_dict == None:
                owner = ''
            else:
                owner = owner_dict.get('name')
            repositories_dict[name] = (owner, link_url, language)
        except Exception, e:
            print e
            continue

    return repositories_dict

def scan_repository_file(repositories_dict):
    '''
    扫描Git仓库中所有的文件及目录
    :return:
    '''
    limit = 10000
    branch = 'master'
    # 用于储存pom.xml文件地址
    pom_dict = {}
    headers = {
        'Cookie': cookie
    }
    for repo_name in repositories_dict.keys():
        try:
            print u'正在扫描仓库: ' + repo_name
            owner, link_url, language = repositories_dict.get(repo_name)
            url = base_url + link_url + '/?at=' + branch + '&limit=' + str(limit)
            response = requests.get(url=url, headers=headers)
            content = json.loads(response.content)
            if content.__contains__('children'):
                values = content.get('children')['values']
                # 判断是否包含pom.xml文件
                contain_pom = False
                for v in values:
                    name = v.get('path')['name']
                    type_ = v.get('type')
                    if type_ == 'FILE' and name == 'pom.xml':
                        contain_pom = True
                if contain_pom:
                    for v in values:
                        name = v.get('path')['name']
                        type_ = v.get('type')
                        if type_ == 'DIRECTORY':
                            _scan_dir(url, name, headers, pom_dict, repo_name)
                        else:
                            if name == 'pom.xml':
                                ll = url.split('?at=')
                                pom_url = ll[0] + '/pom.xml' + '?at=' + ll[1]
                                # print repo_name
                                # print pom_url
                                if pom_dict.__contains__(repo_name):
                                    old = pom_dict.get(repo_name)
                                    new = old + [pom_url]
                                    pom_dict[repo_name] = new
                                else:
                                    pom_dict[repo_name] = [pom_url]
                                # print pom_dict
            else:
                continue
        except Exception, e:
            print e
            continue

    return pom_dict

def _scan_dir(url, dir_name, headers, pom_dict, repo_name):
    '''
    该方法是一个递归方法，用于遍历git上的文件夹
    :return:
    '''
    url_list = url.split('?at=')
    new_url = url_list[0] + '/' + dir_name + '?at=' + url_list[1]
    response = requests.get(url=new_url, headers=headers)
    content = json.loads(response.content)
    # print json.dumps(content)
    # print new_url
    values = content.get('children')['values']
    for v in values:
        try:
            name = v.get('path')['name']
            type_ = v.get('type')
            if type_ == 'DIRECTORY':
                _scan_dir(new_url, name, headers, pom_dict, repo_name)
            else:
                if name == 'pom.xml':
                    ll = new_url.split('?at=')
                    pom_url = ll[0] + '/pom.xml' + '?at=' + ll[1]
                    # print repo_name
                    # print pom_url
                    if pom_dict.__contains__(repo_name):
                        old = pom_dict.get(repo_name)
                        new = old + [pom_url]
                        pom_dict[repo_name] = new
                    else:
                        pom_dict[repo_name] = [pom_url]
                    # print pom_dict
        except Exception, e:
            print e
            continue

def _scan_pom_dependencies(pom_url):
    '''
    该方法用于扫描Java的pom.xml文件，获取其中的dependency相关参数
    :param pom_url: pom.xml文件URL地址
    :return:
    '''
    headers = {
        'Cookie': cookie
    }
    response = requests.get(url=pom_url, headers=headers)
    pom_content = json.loads(response.content)
    dependency_dict = {}
    property_dict = {}

    if pom_content.__contains__('lines'):
        pom_content_list = pom_content.get('lines')
        in_dependencies = False
        in_dependency = False
        in_properties = False
        # version_pattern = re.compile(r'<[a-zA-Z0-9\.\/]+>')
        # u'spring-jms': u'${spring.version}'这种版本信息，在properties中遍历信息
        for line in pom_content_list:
            try:
                line_content = line.get('text').strip()
                if line_content != '' and line_content.find('<!--') == -1:
                    if line_content.find('<properties>') != -1:
                        in_properties = True
                    if line_content.find('</properties>') != -1:
                        in_properties = False
                    if in_properties and line_content != '<properties>':
                        ll2 = line_content.split('</')
                        v_name = ll2[1].split('>')[0]
                        v_value = ll2[0].split('<' + v_name + '>')[1]
                        property_dict['${'+v_name+'}'] = v_value
            except Exception, e:
                print e
                continue
        artifactId = None
        version = None
        for line in pom_content_list:
            try:
                line_content = line.get('text').strip()
                if line_content.find('<dependencies>') != -1:
                    in_dependencies = True
                if line_content.find('</dependencies>') != -1:
                    in_dependencies = False
                    artifactId = None
                    version = None
                if line_content.find('<dependency>') != -1:
                    in_dependency = True
                if line_content.find('</dependency>') != -1:
                    in_dependency = False
                    artifactId = None
                    version = None
                if in_dependencies and in_dependency:
                    if line_content.find('<artifactId>') != -1 and line_content.find('</artifactId>') != -1:
                        artifactId = line_content.split('<artifactId>')[1].split('</artifactId>')[0]
                    if line_content.find('<version>') != -1 and line_content.find('</version>') != -1:
                        version = line_content.split('<version>')[1].split('</version>')[0]
                    if artifactId != None and version != None:
                        if property_dict.__contains__(version):
                            version = property_dict.get(version)
                        dependency_dict[artifactId] = version
                        artifactId = None
                        version = None
            except Exception, e:
                print e
                continue
    return dependency_dict

def _get_eventers(project_name, repository_name):
    '''
    由于直接从Repository中获取的owner信息可能存在离职的情况，因此需要从events数据中获取上传过代码的相关人员，方便追踪
    :param project_name: Project名称
    :param repository_name: Repository名称
    :return:
    '''
    eventer = []
    limit = 50
    headers = {
        'Cookie': cookie
    }
    url = base_url + 'CodeEvents/projects/' + project_name + '/repos/' + repository_name + '/PushedEvents/0/' + str(limit)
    response = requests.get(url, headers=headers).json()
    if response.__contains__('values'):
        values = response.get('values')
        for value in values:
            name = value.get('author')['name']
            if not eventer.__contains__(name):
                eventer.append(name)
    return eventer

def _print_logo():
    print '\n\n'
    print '-' * 68
    print ' $$$$$$\  $$$$$$\ $$$$$$$$\       $$$$$$$\ |$$$$$$$$\ $$$$$$$\  '
    print '$$  __$$\ \_$$  _|\__$$  __|      $$    $$\|$$  _____|$$  __$$\ '
    print '$$ /  \__|  $$ |     $$ |         $$     $$|$$ |      $$ |  $$ |'
    print '$$ |$$$$\   $$ |     $$ |         $$     $$|$$$$$\    $$$$$$$  |'
    print '$$ |\_$$ |  $$ |     $$ |         $$     $$|$$  __|   $$  ____/'
    print '$$ |  $$ |  $$ |     $$ |         $$     $$|$$ |      $$ | '
    print '\$$$$$$  |$$$$$$\    $$ |         $$$$$$$$ |$$$$$$$$\ $$ |  '
    print ' \______/ \______|   \__|         \_______ /\________|\__|  '

    print 'Author: BlackArbiter'
    print 'Version: 0.1'
    print '-'*68
    print '开始扫描......'
    print '>'*28

if __name__ == '__main__':
    _print_logo()
    init()
    for project in project_list:
        print u'Project名称: ' + project
        repositories_dict = get_repositories(project)
        pom_dict = scan_repository_file(repositories_dict)
        for repo_name in repositories_dict.keys():
            try:
                owner, link_url, language = repositories_dict.get(repo_name)
                if pom_dict.__contains__(repo_name):
                    eventers = _get_eventers(project, repo_name)
                    in_ = False
                    for eventer in eventers:
                        if eventer == owner:
                            in_ = True
                            break
                    if not in_:
                        eventers.append(owner)
                    pom_urls = pom_dict.get(repo_name)
                    dependencies_dict = {}
                    for pom_url in pom_urls:
                        dependencies_dict = dict(dependencies_dict, **_scan_pom_dependencies(pom_url))
                    print '----------------------------'
                    print u'仓库名称: ' + repo_name
                    print 'Owner: ' + str(eventers)
                    print 'Language: ' + str(language)
                    print '===============>'
                    for de_name in dependencies_dict.keys():
                        print de_name + ': ' + dependencies_dict.get(de_name)
                    print '<==============='
                    print '----------------------------'
            except Exception, e:
                print e
                continue