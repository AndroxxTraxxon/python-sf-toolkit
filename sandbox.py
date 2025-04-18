import lxml.etree as etree

text = '<?xml version="1.0" encoding="UTF-8"?><foo><bar>baz</bar></foo>'

tree = etree.fromstring(text.encode('utf-8'))

print(tree.findtext(".//bar"))
