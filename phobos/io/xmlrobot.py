from . import representation, xml_factory
from . import sensors
from .base import Representation
from ..utils.transform import create_transformation
from ..utils.tree import get_joints_depth_first


class XMLRobot(Representation):
    SUPPORTED_VERSIONS = ["1.0"]

    def __init__(self, name=None, version=None, links=None, joints=None, materials=None, transmissions=None,
                 sensors=None):
        super().__init__()
        self.name = name
        if version is None:
            version = "1.0"
        elif type(version) is not str:
            version = str(version)
        if version not in self.SUPPORTED_VERSIONS:
            raise ValueError("Invalid version; only %s is supported" % (','.join(self.SUPPORTED_VERSIONS)))

        self.version = version

        self.joints = []
        self.links = []

        self.joint_map = {}
        self.link_map = {}

        self.parent_map = {}
        self.child_map = {}

        if joints is not None:
            for joint in joints:
                self.add_aggregate("joint", joint)
        if links is not None:
            for link in links:
                self.add_aggregate("link", link)

        self.materials = materials if materials is not None else []
        self.transmissions = transmissions if transmissions is not None else []
        self.sensors = sensors if sensors is not None else []

        for entity in self.links + self.sensors:
            entity.link_with_robot(self)
        for entity in self.joints:
            entity.link_with_robot(self)

    def _get_children_lists(self, parentlist, childrenlist, targettype='link'):
        """
        Used recursively. Returns a list of all links that can be considered parents/children for the given parent list
        :param parentlist:
        :param childrenlist:
        :param targettype:
        :return:
        """
        childs = []
        for parent in parentlist:
            childs += self.get_children(parent, targettype=targettype)

        if len(childs) > 0:
            newparents, newchildren = self._get_children_lists(childs, [])
            return parentlist + newparents, childrenlist + childs + newchildren
        else:
            return [], []

    def add_aggregate(self, typeName, elem):
        if typeName in ['joint', 'joints']:
            joint = elem
            self.joint_map[joint.name] = joint
            self.parent_map[joint.child] = (joint.name, joint.parent)
            if joint.parent in self.child_map:
                self.child_map[joint.parent].append((joint.name, joint.child))
            else:
                self.child_map[joint.parent] = [(joint.name, joint.child)]
            if elem not in self.joints:
                self.joints += [elem]
        elif typeName in ['link', 'links']:
            link = elem
            self.link_map[link.name] = link
            if elem not in self.links:
                self.links += [elem]
        else:
            if not typeName.endswith("s"):
                typeName += "s"
            # Collect all instances which have the same name
            instances = []
            # Original list
            objects = getattr(self, typeName)
            for obj in objects:
                if elem.name in obj.name:
                    instances.append(obj.name)
            if instances:
                elem.name += "_{}".format(len(instances))
                print("Renamed object to {}".format(elem.name))
            objects += [elem]
            setattr(self, typeName, objects)

    def add_link(self, link):
        if not isinstance(link, representation.Link):
            raise AssertionError("Please provide an instance of Link to attach.")
        self.add_aggregate('link', link)

    def add_joint(self, joint):
        if not isinstance(joint, representation.Joint):
            raise AssertionError("Please provide an instance of Joint to attach.")
        self.add_aggregate('joint', joint)

    def add_sensor(self, sensor):
        if not isinstance(sensor, sensors.Sensor):
            raise Exception("Please provide an instance of Sensor to attach.")
        self.add_aggregate('sensors', sensor)
        return

    def get_chain(self, root, tip, joints=True, links=True, fixed=True):
        chain = []
        if links:
            chain.append(tip)
        link = tip
        while link != root:
            (joint, parent) = self.parent_map[link]
            if joints:
                if fixed or self.joint_map[joint].joint_type != 'fixed':
                    chain.append(joint)
            if links:
                chain.append(parent)
            link = parent
        chain.reverse()
        return chain

    def get_root(self):
        root = None
        for link in self.link_map:
            if link not in self.parent_map:
                assert root is None, "Multiple roots detected, invalid URDF."
                root = link
        assert root is not None, "No roots detected, invalid URDF."
        return root

    def get_instance(self, targettype, target):
        """
        Returns the id of the given instance
        :param targettype: the tye of the searched instance
        :param target: the name of the searched instance
        :return: the id or None if not found
        """
        if not targettype.endswith("s"):
            targettype += "s"
        for obj in getattr(self, targettype):
            if obj.name == target:
                return obj
        return None

    def get_link(self, link_name, verbose=True) -> [representation.Link, list]:
        """
        Returns the link(s) corresponding to the link name(s).
        :param link_name: the name of the joint to get
        :return: the link instance, None if not found
        """
        if isinstance(link_name, representation.Link):
            return link_name
        if isinstance(link_name, list):
            return [self.get_link(lname) for lname in link_name]

        out = self.get_instance("link", link_name)

        if out is not None:
            return out
        elif verbose:
            print("WARN: Link", link_name, "does not exist!")
            print("These are the existing links:", [ln.name for ln in self.links])
        return None

    def get_joint(self, joint_name, verbose=True) -> [representation.Joint, list]:
        """
        Returns the joint(s) corresponding to the joint name(s).
        :param joint_name: the name of the joint to get
        :return: the joint instance, None if not found
        """
        if isinstance(joint_name, representation.Joint):
            return joint_name
        if isinstance(joint_name, list):
            return [self.get_joint(jname) for jname in joint_name]

        out = self.get_instance("joint", joint_name)

        if out is not None:
            return out
        elif verbose:
            print("WARN: Joint", joint_name, "does not exist!")
            print("These are the existing joints:", [jn.name for jn in self.joints])
        return None

    def get_sensor(self, sensor_name) -> [sensors.Sensor, list]:
        """Returns the ID (index in the sensor list) of the sensor(s).
        """
        if isinstance(sensor_name, list):
            return [self.get_sensor(sensor) for sensor in sensor_name]

        return self.get_instance('sensors', sensor_name)

    def get_inertial(self, link_name):
        """
        Returns the inertial of the given link.
        :param link_name: the name of the respective link
        :return: the inertial of the given link
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        return self.links[link_id].inertial

    def get_visual(self, link_name):
        """
        Return all visuals of the given link if it exists.
        :param link_name: the name of the respective link
        :return: list of visuals of the given link, if there are else none
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        if self.links[link_id].visuals:
            return self.links[link_id].visuals
        else:
            return None

    def get_all_visuals(self):
        visuals = []
        for link in self.links:
            visuals += link.visuals
        return visuals

    def get_visual_by_name(self, visual_name):
        """
        Returns the visual with the given name if it exists
        :param visual_name: name of the searched visual
        :return: the found visual or none
        """
        if isinstance(visual_name, representation.Visual):
            return visual_name
        for link in self.links:
            for vis in link.visuals:
                if vis.name == visual_name:
                    return vis

        return None

    def get_collision(self, link_name):
        """
        Return all collisions of the given link if it exists.
        :param link_name: the name of the respective link
        :return: list of collisions of the given link, if there are else none
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        if self.links[link_id].collisions:
            return self.links[link_id].collisions
        else:
            return None

    def get_all_collisions(self):
        collisions = []
        for link in self.links:
            collisions += link.collisions
        return collisions

    def get_collision_by_name(self, collision_name):
        """
        Returns the collision with the given name if it exists
        :param collision_name: name of the searched collision
        :return: the found collision or none
        """
        if isinstance(collision_name, representation.Collision):
            return collision_name
        for link in self.links:
            for coll in link.collisions:
                if coll.name == collision_name:
                    return coll

        return None

    def get_id(self, targettype, target):
        """
        Returns the id of the given instance
        :param targettype: the tye of the searched instance
        :param target: the name of the searched instance
        :return: the id or None if not found
        """
        for i, obj in enumerate(getattr(self, targettype)):
            if obj.name == target:
                return i
        return None

    def get_joint_id(self, joint_name):
        """
        Returns the ID (index in the joint list) of the joint.
        :param joint_name: the name of the joint to search
        :return: the Id if found else None
        """
        if isinstance(joint_name, list):
            return [self.get_id('joints', name) for name in joint_name]

        return self.get_id('joints', joint_name)

    def get_link_id(self, link_name):
        """
        Returns the ID (index in the link list) of the link.
        :param link_name: the name of the link to search
        :return: the Id if found else None
        """
        if isinstance(link_name, list):
            return [self.get_id('links', name) for name in link_name]

        return self.get_id('links', link_name)

    def get_joint_level(self, jointname):
        """
        Returns the depth of the given joint in the robots kinematic tree
        """
        joint = self.get_joint(jointname)
        return self.get_link_level(joint.parent)

    def get_link_level(self, linkname):
        """
        Returns the depth of the given link in the robots kinematic tree
        """
        parent = self.get_parent(linkname)
        level = 0
        while parent is not None:
            joint = self.get_joint(parent[0])
            parent = self.get_parent(joint.parent)
            level += 1
        return level

    def get_joints_ordered_df(self):
        """Returns the joints in depth first order"""
        return get_joints_depth_first(self, self.get_root())

    def get_links_ordered_df(self):
        """Returns the joints in depth first order"""
        joints = self.get_joints_ordered_df()
        out = [self.get_root()] + [jn.child for jn in joints]
        return [self.get_link(ln) for ln in out]

    def get_material(self, material_name):
        """
        Returns the collision with the given name if it exists
        :param material_name: name of the searched collision
        :return: the found collision or none
        """
        if isinstance(material_name, representation.Material):
            return material_name
        for mat in self.materials:
            if mat.name == material_name:
                return mat

        return None

    def get_parent(self, name, targettype='joint'):
        """
        Get the parent of targettype for the given link name.
        :param name: the name of the joint or link to get the parent for
        :param targettype: the next parent joint or the next parent link (default: 'joint')
        :return: List with one element (todo)
        """
        # Check if the name is present
        if name in self.parent_map.keys():
            parents = self.parent_map[name]
        elif name in self.child_map.keys():
            return None
        else:
            print("Parent map keys: ", self.parent_map.keys())
            raise AssertionError("Nothing with name " + name + " in this robot")

        # Parentmap contains links.
        # If we want joints, then collect the children of these
        assert parents is not None
        if targettype == "link":
            return [parents[1]]
        if targettype == 'joint':
            return [parents[0]]

        return parents

    def get_children(self, name, targettype='joint'):
        """
        Get the children of type targettype for the given link name.
        :param name: the name of the parent link
        :param targettype: whether we want the next joint children or link childrne
        :return: list of children of the given link
        """
        if isinstance(name, list):
            children = []
            for n in name:
                new_children = self.get_children(n, targettype=targettype)
                children += new_children if new_children else []
            return children

        children = []

        if name in self.child_map.keys():
            children = self.child_map[name]

        if children:
            if targettype == 'joint':
                children = [i[0] for i in children]
            elif targettype == 'link':
                children = [i[1] for i in children]

        return children

    def get_leaves(self, start=None):
        """
        Get all leaves of the given start link.
        If start is provided, returns leaves of the sub
        :param start: the root link for which to get the leaves
        :return:
        """
        if not start:
            parentset = set(self.parent_map.keys())
            childset = set(self.child_map.keys())
            return list(parentset - childset)

        if start not in self.parent_map.keys():
            return None

        parents = [start]
        parents, children = self._get_children_lists(parents, [])

        parentset = set(parents)
        childrenset = set(children)

        return parentset, childrenset

    def get_transformation(self, end, start=None):
        """
        Returns the transformation from start to end
        :param end: the end link of the transformation
        :param start: the start link of the transformation (default is root)
        :return: the transformation matrix
        """
        if start is None:
            start = self.get_root()
        transformation = create_transformation((0, 0, 0), (0, 0, 0))

        assert type(end) is str
        assert type(start) is str

        link = end
        while link != start:
            parent = self.get_parent(link)
            if parent is not None and len(parent) > 1:
                print("Multiple parents:", parent, flush=True)
            elif parent is None:
                raise Exception(link, "has no parent, but is different from start", start)
            pjoint = self.get_joint(parent[0])
            transformation = create_transformation(pjoint.origin.xyz, pjoint.origin.rpy).dot(transformation)
            link = pjoint.parent

        return transformation

    def global_origin(self, stop):
        """ Get the global pose of the link.
        """
        return representation.Pose.from_matrix(self.get_transformation(stop))

    def post_read_xml(self):
        """Version and validity check"""
        if self.version is None:
            self.version = "1.0"

        split = self.version.split(".")
        if len(split) != 2:
            raise ValueError("The version attribute should be in the form 'x.y'")

        if split[0] == '' or split[1] == '':
            raise ValueError("Empty major or minor number is not allowed")

        if int(split[0]) < 0 or int(split[1]) < 0:
            raise ValueError("Version number must be positive")

        if self.version not in self.SUPPORTED_VERSIONS:
            raise ValueError("Invalid version; only %s is supported" % (','.join(self.SUPPORTED_VERSIONS)))


xml_factory.class_factory(XMLRobot)
