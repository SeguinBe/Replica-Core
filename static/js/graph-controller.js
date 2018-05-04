/**
 * Created by benoit on 28/09/2016.
 */

angular.module('replicaModule')
    .controller('graphController', function ($scope, $stateParams, $http) {
        $scope.data = {nodes: [], links: []};
        $scope.selection = {
            elements: [],
            removeFromSelection: function (item) {
            if (this.isInSelection(item))
                for (var n = 0; n < this.elements.length; n++) {
                    if (this.elements[n].uid == item.uid) {
                        this.elements.splice(n, 1);
                        break;
                    }
                }
            },
            isInSelection: function(item) {
                return !this.elements.every(function (e) {
                    return item.uid != e.uid
                });
            },
            addToSelection : function(item) {
                if (!this.isInSelection(item)) {
                    this.elements.push(item);
                }
            },
            toggleSelection: function(item) {
                if (!this.isInSelection(item)) {
                    this.addToSelection(item);
                }else{
                    this.removeFromSelection(item);
                }
            }
        };

            function parseParams(param) {
            if (param == null)
                return [];
            if (param instanceof Array)
                return param;
            return [param];
        }

        $scope.groupUid = $stateParams.groupUid;
        $scope.groupData = {};



        $scope.refreshData = function () {
            $http.get(base_api_url+'api/group/'+$scope.groupUid).then(
                function(response) {
                    $scope.groupData = response.data;
                    $scope.queriesUid = $scope.groupData.images.map(function(img) {return img.uid;});
                    $http.post(base_api_url+'api/graph', {image_uids: $scope.queriesUid}).then(
                        function (response) {
                            //TODO Merge more properly so positions are not reseted
                            $scope.data = response.data;
                            //clear arrays
                            /*$scope.data.nodes.length = 0;
                             $scope.data.links.length = 0;
                             Array.prototype.push.apply($scope.data.nodes, response.data.nodes);
                             Array.prototype.push.apply($scope.data.links, response.data.links);
                             var map = new Object();
                             for (var i=0; i<$scope.data.nodes.length;i++) {
                             map[$scope.data.nodes[i].uid] = $scope.data.nodes[i]
                             }
                             for (i=0; i<$scope.data.links.length;i++) {
                             $scope.data.links[i].source = map[$scope.data.links[i].source];
                             $scope.data.links[i].target = map[$scope.data.links[i].target];
                             }*/
                        }, function (response) {
                            $scope.showErrorToast("Error retrieving graph data", response);
                        });
                }, function (response) {
                    $scope.showErrorToast("Error retrieving group data", response);
                });
        };
        $scope.refreshData();
    })
    .directive('imagesGraph', function ($http, $window) {
        function link(scope, el_base) {

            function getImageThumbnail(e) {
                return e.iiif_url + "/full/450,/0/default.jpg";
            }

            var el = el_base[0];
            var width = 800,
                height = $window.innerHeight;

            var base_image_size = 40;
            var image_size = base_image_size;

            var zoom = d3.zoom()
                .scaleExtent([0.5, 10])
                .on("zoom", zoomed);

            var svg = d3.select(el).append("svg")
                .attr("width", '100%')
                .attr("height", height)
                .call(zoom);

            svg.style("opacity", 1e-6)
                .transition()
                .duration(1000)
                .style("opacity", 1);

            var chart = svg
            //.attr("width", width)
            //.attr("height", height);
            //.attr("viewBox", "0 0 " + width + " " + height )
            //.attr("preserveAspectRatio", "xMinYMin")
                .append("g");

            function zoomed() {
                chart.attr("transform", d3.event.transform);
            }

            /*var simulation = d3.forceSimulation()
                .force("link", d3.forceLink().id(function (d) {
                        return d.uid;
                    })
                    .distance(150))
                .force("charge", d3.forceManyBody()
                    .strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .on("tick", ticked);*/

            var centerx = d3.scaleLinear()
                        .range([0, width]);
            var centery = d3.scaleLinear()
                        .range([0, height]);
            var model = new tsnejs.tSNE({
                    dim: 2,
                    perplexity: 10,
                    epsilon: 3
                });

            var simulation = d3.forceSimulation()
                .force('tsne', function (alpha) {
                    // every time you call this, solution gets better
                    model.step();

                    // Y is an array of 2-D points that you can plot
                    var pos = model.getSolution();
                    if (pos) {

                        centerx.domain(d3.extent(pos.map(function (d) {
                            return d[0]
                        })));
                        centery.domain(d3.extent(pos.map(function (d) {
                            return d[1]
                        })));

                        scope.data.nodes.forEach(function (d, i) {
                            if (!d.x) {
                                d.x = 0;
                            }
                            if (!d.y) {
                                d.y = 0;
                            }
                            d.x += alpha * (centerx(pos[i][0]) - d.x);
                            d.y += alpha * (centery(pos[i][1]) - d.y);
                        });
                    }
                    //console.log(model.iter);
                })
                .force('collide', d3.forceCollide().radius(function(d) {return image_size/2;}))
                .on("tick", ticked);

            var link = chart.append("g")
                .attr("class", "links")
                .selectAll("line");

            var node = chart.append("g")
                .attr("class", "nodes")
                .selectAll(".node");

            function dragstarted(d) {
                //if (!d3.event.active) simulation.alphaTarget(0.3).restart();
                simulation.force("tsne", null);
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(d) {
                d.fx = d3.event.x;
                d.fy = d3.event.y;
            }

            function dragended(d) {
                if (!d3.event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            function clickImage(d) {
                scope.$apply( function() {
                    scope.selection.toggleSelection(d);
                })
            }

            function ticked() {
                link
                    .attr("x1", function (d) {
                        return d.source.x;
                    })
                    .attr("y1", function (d) {
                        return d.source.y;
                    })
                    .attr("x2", function (d) {
                        return d.target.x;
                    })
                    .attr("y2", function (d) {
                        return d.target.y;
                    })
                    .attr("class", function (d) {return d.data.type;});

                node
                    .attr("x", function (d) {
                        return d.x - image_size/2;
                    })
                    .attr("y", function (d) {
                        return d.y - image_size/2;
                    })
                    .classed("selected", function(d) {return scope.selection.isInSelection(d);})
            }

            scope.$watch('data', function () {
                console.log(scope.data.nodes.length);

                image_size = base_image_size/Math.sqrt((scope.data.nodes.length+1)/100);

                // Apply the general update pattern to the nodes.

                node = node.data(scope.data.nodes, function (d) {
                    return d.uid;
                });
                node.exit().remove();
                node = node.enter().append("g")
                    //.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; })
                    .attr("class", "node")
                    .append("image")
                    .attr("xlink:href", function (d) {
                        return getImageThumbnail(d);
                    })
                    .attr("width", image_size)
                    .attr("height", image_size)
                    .call(d3.drag()
                        .on("start", dragstarted)
                        .on("drag", dragged)
                        .on("end", dragended))
                    .on("click", clickImage)
                    .merge(node);
                // Apply the general update pattern to the links.
                link = link.data(scope.data.links, function (d) {
                    return d.source.uid + "-" + d.target.uid;
                });
                link.exit().remove();
                link = link.enter().append("line").merge(link);
                //simulation.force("link").links(scope.data.links);
                if (scope.data.nodes.length == 0)
                    return;
                // Update and restart the simulation.
                model.initDataDist(scope.data.distances);
                model.iter = 0;
                simulation.nodes(scope.data.nodes);
                simulation.alphaDecay(0.0001)
                    .alpha(0.02).restart();
            });
            /* scope.$watch(function(){
             width = el.clientWidth;
             height = el.clientHeight;
             return width + height;
             }, resize);

             function resize() {
             console.log('calling resize' + width + height)
             svg.attr("width", width)
             .attr('height', height);
             }*/


        }

        return {
            link: link,
            restrict: 'E',
            scope: {selection: '=', data: '='}
        }
    });