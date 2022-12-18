import re
from vendor._parser import parse_requirement
import sys
import tempfile
import os
import shutil
import io
from  vendor.markers import Marker,_normalize_extra_values,_format_marker
import pathlib
from glob import iglob
from email.message import Message
from email.parser import Parser
from email import message_from_file
from pkg_resources import Requirement, safe_extra, split_sections
from typing import Iterator
import tokenize
import subprocess
from email.policy import EmailPolicy
from email.generator import BytesGenerator, Generator
def _open_setup_script(setup_script):
    if not os.path.exists(setup_script):
        # Supply a default setup.py
        return io.StringIO(u"from setuptools import setup; setup()")

    return getattr(tokenize, 'open', open)(setup_script)
def run_egginfo(srcdir):
	print(srcdir)
	os.chdir(srcdir)
	args = ['python3.9','setup.py', '--name']
	name = subprocess.run(args, stdout=subprocess.PIPE)
	args = [
		'setup.py','egg_info', '--egg-base', '/tmp']
	print(args)
	os.system("python3.9 "+" ".join(args))
	path =  "/tmp/"+name.stdout.decode("utf-8").strip("\n")
	path = path.replace("-", "_")
	path = path + ".egg-info"
	return  path
def license_paths():

	files = set()
	#Prior to those, wheel is entirely responsible for handling license files


	patterns = ("LICEN[CS]E*", "COPYING*", "NOTICE*", "AUTHORS*")

	for pattern in patterns:
		for path in iglob(pattern):
			if path.endswith("~"):
				log.debug(
					f'ignoring license file "{path}" as it looks like a backup'
				)
				continue

			if path not in files and os.path.isfile(path):
				print(
					f'adding license file "{path}" (matched pattern "{pattern}")'
				)
				files.add(path)

	return files
def requires_to_requires_dist(requirement: Requirement) -> str:
    """Return the version specifier for a requirement in PEP 345/566 fashion."""
    if getattr(requirement, "url", None):
        return " @ " + requirement.url

    requires_dist = []
    for op, ver in requirement.specs:
        requires_dist.append(op + ver)

    if requires_dist:
        return " (" + ",".join(sorted(requires_dist)) + ")"
    else:
        return ""
def convert_requirements(requirements: list[str]) -> Iterator[str]:
    """Yield Requires-Dist: strings for parsed requirements strings."""
    for req in requirements:
        parsed_requirement = Requirement.parse(req)
        spec = requires_to_requires_dist(parsed_requirement)
        extras = ",".join(sorted(parsed_requirement.extras))
        if extras:
            extras = f"[{extras}]"

        yield parsed_requirement.project_name + extras + spec
def generate_requirements(
    extras_require: dict[str, list[str]]
) -> Iterator[tuple[str, str]]:
    """
    Convert requirements from a setup()-style dictionary to
    ('Requires-Dist', 'requirement') and ('Provides-Extra', 'extra') tuples.

    extras_require is a dictionary of {extra: [requirements]} as passed to setup(),
    using the empty extra {'': [requirements]} to hold install_requires.
    """
    for extra, depends in extras_require.items():
        condition = ""
        extra = extra or ""
        if ":" in extra:  # setuptools extra:condition syntax
            extra, condition = extra.split(":", 1)

        extra = safe_extra(extra)
        if extra:
            yield "Provides-Extra", extra
            if condition:
                condition = "(" + condition + ") and "
            condition += "extra == '%s'" % extra

        if condition:
            condition = " ; " + condition

        for new_req in convert_requirements(depends):
            yield "Requires-Dist", new_req + condition
def pkginfo_to_metadata(egg_info_path: str, pkginfo_path: str) -> Message:
    """
    Convert .egg-info directory with PKG-INFO to the Metadata 2.1 format
    """
    with open(pkginfo_path, encoding="utf-8") as headers:
        pkg_info = Parser().parse(headers)

    pkg_info.replace_header("Metadata-Version", "2.1")
    # Those will be regenerated from `requires.txt`.
    del pkg_info["Provides-Extra"]
    del pkg_info["Requires-Dist"]
    requires_path = os.path.join(egg_info_path, "requires.txt")
    if os.path.exists(requires_path):
        with open(requires_path) as requires_file:
            requires = requires_file.read()

        parsed_requirements = sorted(split_sections(requires), key=lambda x: x[0] or "")
        for extra, reqs in parsed_requirements:
            for key, value in generate_requirements({extra: reqs}):
                if (key, value) not in pkg_info.items():
                    pkg_info[key] = value

    description = pkg_info["Description"]
    if description:
        description_lines = pkg_info["Description"].splitlines()
        dedented_description = "\n".join(
            # if the first line of long_description is blank,
            # the first line here will be indented.
            (
                description_lines[0].lstrip(),
                textwrap.dedent("\n".join(description_lines[1:])),
                "\n",
            )
        )
        pkg_info.set_payload(dedented_description)
        del pkg_info["Description"]

    return pkg_info

def egg2dist(egginfo_path, distinfo_path):
	"""Convert an .egg-info directory into a .dist-info directory"""

	def adios(p):
		"""Appropriately delete directory, file or link."""
		if os.path.exists(p) and not os.path.islink(p) and os.path.isdir(p):
			shutil.rmtree(p)
		elif os.path.exists(p):
			os.unlink(p)

	adios(distinfo_path)

	if not os.path.exists(egginfo_path):
		# There is no egg-info. This is probably because the egg-info
		# file/directory is not named matching the distribution name used
		# to name the archive file. Check for this case and report
		# accordingly.
		import glob

		pat = os.path.join(os.path.dirname(egginfo_path), "*.egg-info")
		possible = glob.glob(pat)
		err = f"Egg metadata expected at {egginfo_path} but not found"
		if possible:
			alt = os.path.basename(possible[0])
			err += f" ({alt} found - possible misnamed archive file?)"

		raise ValueError(err)

	if os.path.isfile(egginfo_path):
		# .egg-info is a single file
		pkginfo_path = egginfo_path
		pkg_info = pkginfo_to_metadata(egginfo_path, egginfo_path)
		#os.mkdir(distinfo_path)
	else:
		# .egg-info is a directory
		pkginfo_path = os.path.join(egginfo_path, "PKG-INFO")
		pkg_info = pkginfo_to_metadata(egginfo_path, pkginfo_path)

		# ignore common egg metadata that is useless to wheel
		shutil.copytree(
			egginfo_path,
			distinfo_path,
			ignore=lambda x, y: {
				"PKG-INFO",
				"requires.txt",
				"SOURCES.txt",
				"not-zip-safe",
			},
		)

		# delete dependency_links if it is only whitespace
		dependency_links_path = os.path.join(distinfo_path, "dependency_links.txt")
		with open(dependency_links_path) as dependency_links_file:
			dependency_links = dependency_links_file.read().strip()
		if not dependency_links:
			adios(dependency_links_path)

	pkg_info_path = os.path.join(distinfo_path, "METADATA")
	serialization_policy = EmailPolicy(
		utf8=True,
		mangle_from_=False,
		max_line_length=0,
	)
	with open(pkg_info_path, "w", encoding="utf-8") as out:
		Generator(out, policy=serialization_policy).flatten(pkg_info)

	for license_path in license_paths():
		filename = os.path.basename(license_path)
		if os.path.exists(filename):
			shutil.copy(license_path, os.path.join(distinfo_path, filename))


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


#if sys.version_info >= (3, 8):
#    import importlib.metadata as importlib_metadata
#else:
#    import importlib_metadata

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
path = os.path.join(tempfile.mkdtemp(), 'dist-info')

#path = pathlib.Path(build.ProjectBuilder(os.fspath(port)).metadata_path(tmpdir))

#, runner = pep517.quiet_subprocess_runner

print(path)
egginfodir = run_egginfo(port)

print(egginfodir)
#TODO get the name of egginfo dir

egg2dist(egginfodir, path)
metadata =message_from_file(open(path+"/METADATA","r"))
if os.path.exists(egginfodir) and not os.path.islink(egginfodir) and os.path.isdir(egginfodir) and egginfodir.startswith("/tmp"):
	shutil.rmtree(egginfodir)

print(metadata)
for d in compute_dependencies(set(sys.argv[2:]),metadata):
	print(d.name,d.specifier,end="")
	if d.marker:
		print(" (",end="")
		print(_format_marker(d.marker),end="")
		print(")",end="")
	print("")