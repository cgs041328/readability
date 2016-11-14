from flask import Flask
from readability import Readability

app = Flask(__name__)
@app.route('/')
def index():
    return 'Index Page'
@app.route('/article/<path:inputUrl>')
def read(inputUrl):
    if(not inputUrl.startswith('http')):
        inputUrl = 'http://'+inputUrl
    article = getReadableArticle(inputUrl)
    return "<h1>"+article.title+"</h1>"+article.content

def getReadableArticle(url):
    res = requests.get(url)
    if res.status_code != requests.codes.ok:
        return None
    rawHtml = res.text
    article = Readability(rawHtml,url)
    # if article is not None:
    #     with open(url.split('/')[-1].split('?')[0]+'.html', 'w+') as out:
    #         out.write(article.content)
    return article

if __name__ == '__main__':
    app.run(debug=True)