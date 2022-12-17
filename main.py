import re
from vendor._parser import parse_requirement
import sys
import tempfile
import os
from  vendor.markers import Marker,_normalize_extra_values,_format_marker
import pathlib
import pep517
from email import message_from_file
if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata

if len(sys.argv) != 1:
	port = sys.argv[1]
else:
	port = "/usr/ports/devel/py-twisted/work-py39/Twisted-22.10.0"
	"""
	print(ProjectBuilder("/usr/ports/devel/py-twisted/work-py39/Twisted-22.10.0/").prepare('sdist','/tmp/test1',None));
  File "/usr/local/lib/python3.9/site-packages/build/__init__.py", line 399, in prepare
    return self._call_backend(
  File "/usr/local/lib/python3.9/site-packages/build/__init__.py", line 465, in _call_backend
    callback = getattr(self._hook, hook_name)
AttributeError: 'Pep517HookCaller' object has no attribute 'prepare_metadata_for_build_sdist'
	"""
with tempfile.TemporaryDirectory() as tmpdir:
	#TODO take more combinations from build.ProjectBuilder
	#path = pathlib.Path(build.ProjectBuilder(os.fspath(port),runner=pep517.quiet_subprocess_runner).metadata_path(tmpdir))
	f = pep517.wrappers.Pep517HookCaller(port,'setuptools.build_meta',runner=pep517.quiet_subprocess_runner).prepare_metadata_for_build_wheel(tmpdir,None,False)
	metadata =message_from_file(open(tmpdir+"/"+f+"/METADATA","r"))

def compute_dependencies(extras,metadata):
	contexts: Sequence[Dict[str, str]] = [{"extra": re.sub('[^A-Za-z0-9.-]+', '_', e).lower()} for e in extras]

	for req_string in metadata.get_all("Requires-Dist", []):
		req = parse_requirement(req_string)
		if req.marker:
			marker = Marker.__new__(Marker)
			marker._markers = _normalize_extra_values(req.marker)
			#print(marker._markers)
		if not req.marker:
			yield req
		elif not extras and marker.evaluate({"extra": ""}):
			yield req
		elif any(marker.evaluate(context) for context in contexts):
			yield req

print(metadata)
for d in compute_dependencies(set(sys.argv[2:]),metadata):
	print(d.name,d.specifier,end="")
	if d.marker:
		print(" (",end="")
		print(_format_marker(d.marker),end="")
		print(")",end="")
	print("")
