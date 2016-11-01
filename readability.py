from __future__ import division
import os
import sys
import urllib
from urllib import parse
import re
from html.parser import HTMLParser
import math
import posixpath
import chardet
from bs4 import BeautifulSoup


class Readability:

    regexps = {
        'unlikelyCandidates': re.compile("banner|combx|comment|community|disqus|extra|foot|header|menu|modal|related|remark|rss|share|shoutbox|sidebar|skyscraper|sponsor|ad-break|agegate|pagination|pager|popup",re.I),
        'okMaybeItsACandidate': re.compile("and|article|body|column|main|shadow", re.I),
        'positive': re.compile("article|body|content|entry|hentry|h-entry|main|page|pagination|post|text|blog|story",re.I),
        'negative': re.compile("hidden|^hid$| hid$| hid |^hid |banner|combx|comment|com-|contact|foot|footer|footnote|masthead|media|meta|modal|outbrain|promo|related|scroll|share|shoutbox|sidebar|skyscraper|sponsor|shopping|tags|tool|widget", re.I),
        'extraneous': re.compile("print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|sign|single|utility",re.I),
        'divToPElements': re.compile("<(a|blockquote|dl|div|img|ol|p|pre|table|ul)",re.I),
        'replaceBrs': re.compile("(<br[^>]*>[ \n\r\t]*){2,}",re.I),
        'replaceFonts': re.compile("<(/?)font[^>]*>",re.I),
        'killBreaks': re.compile("(<br\s*/?>(\s|&nbsp;?)*)+",re.I),
        'videos': re.compile("//(www\.)?(dailymotion|youtube|youtube-nocookie|player\.vimeo|youku|tudou|56|yinyuetai)\.com",re.I),
        'link':re.compile("<a[^>]*>(.*?)</a>",re.I),
        'title':re.compile(r"(?<=<title>).*?(?=</title>)",re.I),
    }

    tagNamesToScore =  ["section","h2","h3","h4","h5","h6","p","td","pre"]

    def __init__(self, input_html, url):
        self.candidates = {}
        self.raw_html = input_html
        self.input_html = input_html
        self.url = url
        self.prepareDocument()
        self.title = self.getArticleTitle()
        self.content = self.grabArticle()

    def prepareDocument(self):
        self.input_html = self.regexps['replaceBrs'].sub("</p><p>", self.input_html)
        self.input_html = self.regexps['replaceFonts'].sub("<\g<1>span>", self.input_html)
        self.html = BeautifulSoup(self.input_html, 'html.parser')
        self.removeUnnecessaryElements()

    def removeUnnecessaryElements(self):
        for elem in self.html.find_all("script"):
            elem.extract()
        for elem in self.html.find_all("noscript"):
            elem.extract()
        for elem in self.html.find_all("style"):
            elem.extract()
        for elem in self.html.find_all("link"):
            elem.extract()

    def grabArticle(self):
        #score elements
        elementsToScore = []
        for elem in self.html.find_all(True):
            unlikelyMatchString = elem.get('id','')+''.join(elem.get('class',''))
            if self.regexps['unlikelyCandidates'].search(unlikelyMatchString) and \
                not self.regexps['okMaybeItsACandidate'].search(unlikelyMatchString) and \
                elem.name != 'body':
                elem.extract()
                continue
            if elem.name in self.tagNamesToScore:
                elementsToScore.append(elem)
            if elem.name == 'div':
                s = elem.encode_contents()
                if not self.regexps['divToPElements'].search(s.decode()):
                    elem.name = 'p'
                    elementsToScore.append(elem)
        for node in elementsToScore:
            parentNode = node.parent
            if not parentNode:
                continue
            innerText = node.text
            if len(innerText) < 25:
                continue
            grandParentNode = parentNode.parent
            parentHash = hash(str(parentNode))
            if parentHash not in self.candidates:
                self.candidates[parentHash] = self.initializeNode(parentNode)
            grandParentHash = hash(str(grandParentNode))
            if grandParentNode and grandParentHash not in self.candidates:
                self.candidates[grandParentHash] = self.initializeNode(grandParentNode)
            contentScore = 1
            contentScore += len(innerText.replace('，', ',').split(','))
            contentScore +=  min(math.floor(len(innerText) / 100), 3)
            self.candidates[parentHash]['score'] += contentScore
            if grandParentNode:
                self.candidates[grandParentHash]['score'] += contentScore / 2
        #end
        #find top candidate
        topCandidate = None
        for key in self.candidates:
            self.candidates[key]['score'] = self.candidates[key]['score'] * \
                                            (1 - self.getLinkDensity(self.candidates[key]['node']))

            if not topCandidate or self.candidates[key]['score'] > topCandidate['score']:
                topCandidate = self.candidates[key]
        #end
        # articleContent = self.html.new_tag("div",id='eudic-reader-content')
        articleContent = ''
        if topCandidate:
            #     #look through its siblings for content that might also be related, a little slow
            # siblingScoreThreshold = max(10,topCandidate['score']*0.2)
            # if topCandidate['node'].parent:
            #     siblingNodes = topCandidate['node'].parent.children
            #     for sibling in siblingNodes:
            #         append = False
            #         siblingHash = hash(str(sibling))
            #         if sibling == topCandidate['node']:
            #             append = True
            #         elif siblingHash in self.candidates and self.candidates[siblingHash]['score'] >= siblingScoreThreshold:
            #             append = True
            #         elif sibling.name == 'p':
            #             linkDensity = self.getLinkDensity(sibling)
            #             nodeLength = len(sibling.text)
            #             if nodeLength >80 and linkDensity< 0.25:
            #                 append = True
            #         if(append):
            #             articleContent.append(sibling)
            # else:
            #     articleContent = topCandidate['node']
            articleContent = topCandidate['node']
            articleContent = self.prepareArticle(articleContent)
        return articleContent

    def cleanLink(self,content):
        return self.regexps['link'].sub(r'\1', content)

    def prepareArticle(self, content):
        self.cleanStyle(content)
        self.clean(content, 'object')
        self.cleanConditionally(content, "form")
        self.clean(content, 'embed')
        self.clean(content, 'footer')
        self.clean(content, 'fieldset')

        if len(content.find_all('h1')) == 1:
            self.clean(content, 'h1')       
        if len(content.find_all('h2')) == 1:
            self.clean(content, 'h2')

        self.clean(content, 'iframe')
        self.cleanHeaders(content)

        self.cleanConditionally(content, "table")
        self.cleanConditionally(content, "ul")
        self.cleanConditionally(content, "div")

        #remove extra paragraphs
        for pElem in content.find_all('p'):
            count = len(pElem.find_all('img'))+len(pElem.find_all('embed'))+len(pElem.find_all('object'))+len(pElem.find_all('iframe'))
            if count == 0 and len(pElem.text) == 0:
                pElem.extract()

        self.fixImagesPath(content)
        self.description = content.text[:200]
        content = self.killBreaks(content)
        #clean external links if needed
        #content = self.cleanLink(content)
        return content

    def clean(self,e ,tag):

        targetList = e.find_all(tag)
        isEmbed = 0
        if tag =='object' or tag == 'embed':
            isEmbed = 1

        for target in targetList:
            attributeValues = ""
            for attribute in target.attrs:
                #
                get_attr = target.get(attribute[0])
                attributeValues += get_attr if get_attr is not None else ''

            if isEmbed and self.regexps['videos'].search(attributeValues):
                continue

            if isEmbed and self.regexps['videos'].search(target.encode_contents().decode()):
                continue
            target.extract()

    def cleanStyle(self, e):
        for elem in e.find_all(True):
            del elem['class']
            del elem['id']
            del elem['style']

    def cleanConditionally(self, e, tag):
        tagsList = e.find_all(tag)

        for node in tagsList:
            weight = self.getClassWeight(node)
            hashNode = hash(str(node))
            if hashNode in self.candidates:
                contentScore = self.candidates[hashNode]['score']
            else:
                contentScore = 0

            if weight + contentScore < 0:
                node.extract()
            else:
                p = len(node.find_all("p"))
                img = len(node.find_all("img"))
                li = len(node.find_all("li"))-100
                input_html = len(node.find_all("input_html"))
                embedCount = 0
                embeds = node.find_all("embed")
                for embed in embeds:
                    if not self.regexps['videos'].search(embed['src']):
                        embedCount += 1
                linkDensity = self.getLinkDensity(node)
                contentLength = len(node.text)
                toRemove = False

                if img > p:
                    toRemove = True
                elif li > p and tag != "ul" and tag != "ol":
                    toRemove = True
                elif input_html > math.floor(p/3):
                    toRemove = True
                elif contentLength < 25 and (img==0 or img>2):
                    toRemove = True
                elif weight < 25 and linkDensity > 0.2:
                    toRemove = True
                elif weight >= 25 and linkDensity > 0.5:
                    toRemove = True
                elif (embedCount == 1 and contentLength < 35) or embedCount > 1:
                    toRemove = True

                if toRemove:
                    node.extract()

    def cleanHeaders(self,node):
        for headerIndex in range(1,4):
            headers = node.find_all('h'+str(headerIndex))
            for header in headers:
                if self.getClassWeight(header)<0:
                    header.extract()

    def getArticleTitle(self):
        title = ''
        try:
            title = self.html.find('title').text
        except:
            title = self.regexps['title'].search(self.raw_html).group(0)
        return title

    def initializeNode(self, node):
        contentScore = 0
        if node.name == 'div':
            contentScore += 5;
        elif node.name in ['blockquote','pre','td']:
            contentScore += 3;
        elif node.name in ['form','address','ol','ul','dl','dd','dt','li']:
            contentScore -= 3;
        elif node.name in ['th','h1','h2','h3','h4','h5','h6']:
            contentScore -= 5;
        contentScore += self.getClassWeight(node)

        return {'score':contentScore, 'node': node}

    def getClassWeight(self, node):
        weight = 0
        if 'class' in node:
            if self.regexps['negative'].search(node['class']):
                weight -= 25
            if self.regexps['positive'].search(node['class']):
                weight += 25

        if 'id' in node:
            if self.regexps['negative'].search(node['id']):
                weight -= 25
            if self.regexps['positive'].search(node['id']):
                weight += 25

        return weight

    def getLinkDensity(self, node):
        links = node.find_all('a')
        textLength = len(node.text)

        if textLength == 0:
            return 0
        linkLength = 0
        for link in links:
            linkLength += len(link.text)

        return linkLength / textLength

    def fixImagesPath(self, node):
        imgs = node.find_all('img')
        for img in imgs:
            src = img.get('src',None)
            if not src:
                img.extract()
                continue

            if 'http://' != src[:7] and 'https://' != src[:8]:
                newSrc = ''
                if '//' == src[:2]:
                    newSrc = 'http:' + src
                else:
                    newSrc = parse.urljoin(self.url, src)

                newSrcArr = parse.urlparse(newSrc)
                newPath = posixpath.normpath(newSrcArr[2])
                newSrc = parse.urlunparse((newSrcArr.scheme, newSrcArr.netloc, newPath,
                                              newSrcArr.params, newSrcArr.query, newSrcArr.fragment))
                img['src'] = newSrc

    def killBreaks(self,content):
        content = content.encode_contents()
        content = self.regexps['killBreaks'].sub("<br />", content.decode())
        return content

