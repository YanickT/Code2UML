from typing import List, Optional, Tuple, Dict
import os
import re

IMPORTPATTERN1 = r"[\n|^]import ([\w\.]*).*\n"
IMPORTPATTERN2 = r"from (\w*) import .*\n"

CLASSPATTERN = r"\n(class [\s\S]*?(?=\n\w|\Z))"
METHODPATTERN = r"def [\s\S]*?(?=\n\w|\Z)"
FUNCPATTERN = r"\ndef (\w*)\("


class Code2UML:
    """
    Each subfile will be interpreted as own module
    Each module will have its own subcluster with name as label
    Each class will be represented with its attributes and methods as a box in the subcluster
    All functions will be shown in a single "tab"-shaped object in the subcluster
    Each dependency will be indicated by a dashed arrow
    Each inheritance will be indicated by a straight arrow with empty head
    """

    def __init__(self, path: str, ownmodule: Optional[str] = None, ignore: List[str] = []):
        """
        Initializes the Code2UML class
        :param path: str = path to directory with .py files
        :param ownmodule: Optional[str] = name of the package (for preventing package.<submodule> import problems)
        :param ignore: List[str] = list of files/folders to ignore
        """
        if not os.path.isdir(path):
            raise AttributeError("Path does not lead to a folder!")
        self.path = path
        self.ownmodule = ownmodule

        # detect all files
        folders = [""]
        self.files = []
        for path in folders:
            files = os.listdir(f"{self.path}/{path}")
            for file in files:
                if file in ignore:
                    continue
                if os.path.isdir(f"{self.path}/{path}{file}"):
                    folders.append(f"{path}{file}/")
                elif file[-3:] == ".py" and not ("__init__" in file):
                    self.files.append(f"{self.path}/{path}{file}")

        # create structure fore each file
        self.modules = []
        for file in self.files:
            print(f"File: {file} ", end="")

            with open(file, "r") as doc:
                text = "".join(doc.readlines())

            # check for imports
            imports_ = re.findall(IMPORTPATTERN1, text)
            imports_ += re.findall(IMPORTPATTERN2, text)
            imports = []
            for name in imports_:
                if "." in name:
                    module_parts = name.split(".")
                    if module_parts[0] == self.ownmodule:
                        imports.append(module_parts[-1])
                    else:
                        imports.append(module_parts[0])
                else:
                    imports.append(name)

            # extract all classes
            classes, relations = self._extract_classes(text)

            # extract functions
            functions = re.findall(FUNCPATTERN, text)

            name = file.split("/")[-1].split(".")[0]
            self.modules.append((name, imports, classes, functions, relations))
            print("done")

    def _extract_classes(self, text: str, separator: str = "    ") -> Tuple[
        List[Dict[str: str]], List[Tuple[str, str, str]]]:
        """
        Protected! Extract class information from .py-file
        :param text: str = content of .py-file
        :param separator: str = separator used for indentation in the .py-file
        :return: List[Dict[str: str]], List[Tuple[str, str, str]]] = class_information, relationship-information
        """
        classes = []
        relations = []
        classes_text = re.findall(CLASSPATTERN, text)
        for class_text in classes_text:
            # extract name and superclass
            headline = class_text.split("\n")[0]
            name = re.findall(r"^class (\w*)(?:|\()", headline)[0]
            superclass = re.findall(r"^class \w*\((\w*)\):", headline)
            if len(superclass) == 0:
                superclass = None
            else:
                superclass = superclass[0]
                relations.append((superclass, name, "extend"))

            # extract methods
            class_text = class_text.replace(f"\n{separator}", "\n")
            methods = re.findall(METHODPATTERN, class_text)
            method_names = [re.findall(r"^def (\w*)(?:|\()", method)[0] for method in methods]

            # extract attributes
            try:
                init_index = method_names.index("__init__")
                attributes = re.findall(r"self.(\w*) =", methods[init_index])

            except ValueError:
                attributes = []

            classes.append({
                "name": name,
                "superclass": superclass,
                "methods": method_names,
                "attributes": attributes
            })
        return classes, relations

    def graphviz(self) -> str:
        """
        Generates .dot representation of the UML structure
        :return: str = .dot representation of the UML structure
        """
        graph = "digraph UmlDiagram {\n  node[shape=record, sytle=filled, fillcolor=gray95]\n"
        graph += """  nodesep="0.5"\n  ranksep="5.0"\n  compound=true\n"""
        clusters = {}
        for i, module in enumerate(self.modules):  # (name, imports, classes, functions, relations)
            subgraph = f"  subgraph cluster{i}{{\n    label = <Module: <B>{module[0]}</B>>\n    labeljust=l\n"

            # add classes
            for c in module[2]:
                subgraph += "  " + self._graphviz_class(c)

            if module[2]:
                # this is the default one. It will be overwritten if a function exists but we dont care
                clusters[module[0]] = (f"{module[2][0]['name']}Class", i)

            # add functions
            if module[3]:
                subgraph += "  " + self._graphviz_functions(module[0], module[3])
                clusters[module[0]] = (f"{module[0]}Functions", i)

            subgraph += "  }"
            graph += "\n" + subgraph + "\n\n"

        # relations are used at last
        external = []
        for module in self.modules:
            # add import relations
            for dependency in module[1]:
                end, end_i = clusters[module[0]]
                if dependency in clusters:
                    start, start_i = clusters[dependency]

                    # xlabel="dependency"
                    graph += f"""  {start} -> {end}[arrowhead=vee style=dashed """ + \
                             f"""ltail = cluster{start_i} lhead = cluster{end_i} tailport=s]\n"""
                else:
                    graph += f"""  {dependency}[shape="folder"]"""
                    external.append(dependency)
                    # xlabel="dependency"
                    graph += f"""  {dependency} -> {end}[arrowhead=vee style=dashed  """ + \
                             f"""lhead = cluster{end_i} tailport=s]\n"""

            # add relations between classes
            for start, end, kind in list(set(module[4])):
                # xlabel="extends"
                graph += f"""  {start}Class -> {end}Class[dir=back arrowtail=empty headport=n, tailport=s]\n"""

        # set external packages to same rank
        graph += f"""{{rank = same; {"; ".join([str(n) for n in list(set(external))])}}}\n\n"""
        graph += "}"
        return graph

    def _graphviz_class(self, c: Dict[str, str]) -> str:
        """
        Generates a .dot representation for a single class
        :param c: Dict[str, str] = {"name", "attributes", "methods"}
        :return: .dot representation for class c
        """
        string = f"""{c['name']}Class [\n"""
        string += """  shape=plain\n  label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">\n"""

        # for name
        string += f"""    <tr> <td> <b>{c['name']}</b> </td> </tr>\n"""

        # for attributes
        if c["attributes"]:
            string += "    <tr> <td>\n"
            string += """      <table border="0" cellborder="0" cellspacing="0" >\n"""
            string += """        <tr> <td align="left" >+ property</td> </tr>\n"""
            for attri in c["attributes"]:
                string += f"""        <tr> <td port="ss1" align="left" >- {attri}</td> </tr>\n"""
            string += "      </table>\n"
            string += """    </td> </tr>\n"""

        # for methods
        if c["methods"]:
            string += "    <tr> <td>\n"
            string += """      <table border="0" cellborder="0" cellspacing="0" >\n"""
            string += """        <tr> <td align="left" >+ method</td> </tr>\n"""
            for method in c["methods"]:
                string += f"""        <tr> <td port="ss1" align="left" >- {method}</td> </tr>\n"""
            string += "      </table>\n"
            string += """    </td> </tr>\n"""

        # close table
        string += "  </table>>]\n\n"
        return string

    def _graphviz_functions(self, name: str, fs: List[str]) -> str:
        """
        Generates a .dot representation for all functions
        :param name: str = module name
        :param fs: List[str] = list of function names
        :return: .dot representation of all functions in module
        """
        string = f"""{name}Functions [\n"""
        string += """    shape="folder"\n """
        string += """    label= <<table border="0" cellborder="1" cellspacing="0" cellpadding="4">\n"""

        string += """        <tr> <td align="left" >+ functions</td> </tr>\n"""
        for f in fs:
            string += f"""        <tr> <td port="ss1" align="left" >- {f}</td> </tr>\n"""

        string += "  </table>>]\n\n"
        return string

    def export_dot(self, path: str):
        """
        Generates a .dot representation of the UML diagram and saves it at path
        :param path: str = path where the file should be saved
        :return: void
        """
        with open(f"{path}.dot", "w") as doc:
            doc.write(self.graphviz())


if __name__ == "__main__":
    path = "../Pyrror"
    converter = Code2UML(path, ownmodule="pyrror", ignore=["setup.py", "gitignore", "test", "update", "constants.py"])
    converter.export_dot("pyrror")
